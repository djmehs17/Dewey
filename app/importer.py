from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from rapidfuzz import fuzz, process

from .database import Database
from .integrations.audiobookshelf import AudiobookshelfClient
from .integrations.mam import MamClient
from .integrations.metadata import MetadataClient, MetadataResult
from .integrations.qbit import QbitClient, hash_from_magnet, is_complete, resolve_source_root
from .library import nudge_library_watchers
from .settings import DeweySettings, SettingsManager
from .utils import (
    clean_release_text,
    collect_audio_files,
    collect_ebook_files,
    link_or_copy,
    parse_release_name,
    safe_path_component,
    unique_destination,
)


def _metadata_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def _looks_like_author(value: str | None, author: str | None) -> bool:
    if not value or not author:
        return False
    return fuzz.token_set_ratio(clean_release_text(value).lower(), clean_release_text(author).lower()) >= 90


def _strip_author_from_release(release_title: str, author: str | None) -> str | None:
    if not release_title or not author:
        return None
    cleaned = clean_release_text(release_title)
    author_pattern = r"\s+".join(re.escape(part) for part in clean_release_text(author).split())
    patterns = (
        rf"^\s*{author_pattern}\s*(?:-|:|by)\s*(?P<title>.+)$",
        rf"^(?P<title>.+?)\s*(?:-|:|by)\s*{author_pattern}\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned, flags=re.I)
        if match:
            title = match.group("title").strip(" .-_")
            return title or None
    return None


def _title_candidate(
    release_title: str,
    author_hint: str | None,
    *,
    include_series_in_title: bool,
) -> tuple[str | None, str | None, int]:
    parsed = parse_release_name(release_title, include_series_in_title=include_series_in_title)
    if parsed.title and not _looks_like_author(parsed.title, author_hint):
        return parsed.title, parsed.series, parsed.confidence

    stripped = _strip_author_from_release(release_title, author_hint)
    if stripped:
        stripped_parsed = parse_release_name(stripped, include_series_in_title=include_series_in_title)
        title = stripped_parsed.title or stripped
        if title and not _looks_like_author(title, author_hint):
            confidence = max(parsed.confidence, stripped_parsed.confidence, 76)
            return title, stripped_parsed.series or parsed.series, confidence

    return parsed.title or clean_release_text(release_title) or None, parsed.series, parsed.confidence


def _apply_series_to_title(title: str | None, series: str | None, enabled: bool) -> str | None:
    if not title:
        return None
    if not enabled or not series:
        return title
    cleaned_title = clean_release_text(title).lower()
    cleaned_series = clean_release_text(series).lower()
    if cleaned_series and cleaned_series not in cleaned_title:
        return f"{series} - {title}"
    return title


class ImportManager:
    def __init__(self, db: Database, settings_manager: SettingsManager):
        self.db = db
        self.settings_manager = settings_manager
        self.tasks: dict[int, asyncio.Task[None]] = {}

    def start(self, job_id: int) -> None:
        task = self.tasks.get(job_id)
        if task and not task.done():
            return
        self.tasks[job_id] = asyncio.create_task(self.run(job_id))

    def resume_pending(self) -> None:
        for job_id in self.db.pending_job_ids():
            self.db.add_event(job_id, "info", "Resuming import after Dewey startup")
            self.start(job_id)

    async def run(self, job_id: int) -> None:
        try:
            await self._run(job_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - log unexpected import failures to the job.
            self.db.update_job(job_id, status="error", error=str(exc))
            self.db.add_event(job_id, "error", str(exc))
        finally:
            task = self.tasks.get(job_id)
            if task is asyncio.current_task():
                self.tasks.pop(job_id, None)

    async def _run(self, job_id: int) -> None:
        settings = self.settings_manager.get()
        row = self.db.get_job_row(job_id)
        if row is None:
            return

        result = json.loads(row["result_json"])
        media_type = self._job_media_type(row, result)
        category = result.get("_category") or settings.qbittorrent_category
        torrent_url = result.get("magnet_url") or result.get("download_url") or row["torrent_url"]
        if not torrent_url:
            raise RuntimeError("Selected result did not include a torrent or magnet URL.")

        torrent_title = result.get("title") or row["torrent_title"]
        expected_hash = hash_from_magnet(torrent_url)
        qbit = QbitClient(settings)

        if row["status"] == "queued":
            self.db.update_job(job_id, status="downloading", progress=0)
            self.db.add_event(job_id, "info", "Sending torrent to qBittorrent")
            if result.get("requires_dewey_download") or result.get("provider") == "mam":
                torrent_bytes, filename = await MamClient(settings).download_torrent(result)
                await qbit.add_torrent_file(torrent_bytes, filename, category)
            else:
                await qbit.add_torrent(torrent_url, category)
            self.db.add_event(job_id, "info", "Torrent accepted by qBittorrent")

        torrent = await self._wait_for_completion(
            job_id=job_id,
            qbit=qbit,
            category=category,
            torrent_title=torrent_title,
            expected_hash=expected_hash or row["torrent_hash"],
            settings=settings,
        )

        self.db.update_job(job_id, status="importing")
        if media_type == "ebook":
            self.db.add_event(job_id, "info", "Download complete; preparing ebook import")
            await self._complete_ebook_import(job_id, torrent, result, settings, qbit)
        else:
            self.db.add_event(job_id, "info", "Download complete; preparing audiobook import")
            await self._complete_import(job_id, torrent, result, settings, qbit)

    @staticmethod
    def _job_media_type(row: Any, result: dict[str, Any]) -> str:
        candidate = result.get("_media_type")
        if not candidate:
            try:
                candidate = row["media_type"]
            except (IndexError, KeyError):
                candidate = None
        return candidate if candidate in {"audiobook", "ebook"} else "audiobook"

    async def _wait_for_completion(
        self,
        *,
        job_id: int,
        qbit: QbitClient,
        category: str,
        torrent_title: str,
        expected_hash: str | None,
        settings: DeweySettings,
    ) -> dict[str, Any]:
        missing_count = 0
        while True:
            torrent = await qbit.find_torrent(
                category=category,
                title=torrent_title,
                expected_hash=expected_hash,
            )
            if torrent is None:
                missing_count += 1
                if missing_count in {1, 5, 20}:
                    self.db.add_event(job_id, "warning", "Waiting for qBittorrent to expose the added torrent")
                await asyncio.sleep(settings.monitor_interval_seconds)
                continue

            torrent_hash = torrent.get("hash")
            if torrent_hash:
                self.db.update_job(job_id, torrent_hash=torrent_hash)
            progress = float(torrent.get("progress") or 0)
            self.db.update_job(job_id, progress=round(progress, 4))
            if is_complete(torrent):
                self.db.update_job(job_id, progress=1)
                return torrent
            await asyncio.sleep(settings.monitor_interval_seconds)

    async def _complete_import(
        self,
        job_id: int,
        torrent: dict[str, Any],
        result: dict[str, Any],
        settings: DeweySettings,
        qbit: QbitClient,
    ) -> None:
        source_root = resolve_source_root(torrent, settings.torrents_dir)
        files = await self._resolve_media_files(torrent, source_root, qbit, collect_audio_files)
        if not files:
            raise RuntimeError(f"No audio files were found under {source_root}")

        self.db.update_job(job_id, download_path=str(source_root))
        self.db.add_event(job_id, "info", f"Found {len(files)} audio file(s)")

        metadata, warning = await self._resolve_metadata(result, settings)
        warnings: list[str] = []
        if warning:
            warnings.append(warning)
            self.db.add_event(job_id, "warning", warning)
        metadata_summary = self._metadata_summary(metadata)
        if metadata_summary:
            self.db.add_event(job_id, "info", metadata_summary)

        destination, needs_review, author_match, match_score = self._destination_for(
            metadata=metadata,
            torrent_title=result.get("title") or str(torrent.get("name") or "Untitled"),
            settings=settings,
        )
        destination = unique_destination(destination)
        staging_destination = self._staging_destination(job_id, destination, settings)
        if staging_destination.exists():
            shutil.rmtree(staging_destination)
        staging_destination.mkdir(parents=True, exist_ok=True)

        if needs_review:
            review_reason = self._metadata_review_reason(metadata, settings)
            if review_reason:
                warnings.append(review_reason)
                self.db.add_event(job_id, "warning", review_reason)
            self.db.add_event(job_id, "warning", f"Import requires manual review in {destination}")
        else:
            self.db.add_event(job_id, "info", f"Importing into staging area for {destination}")

        copy_count = 0
        source_base = source_root if source_root.is_dir() else source_root.parent
        for src in files:
            try:
                relative = src.relative_to(source_base)
            except ValueError:
                relative = Path(src.name)
            target = staging_destination / relative
            try:
                mode, _ = link_or_copy(src, target)
            except OSError as exc:
                raise RuntimeError(f"Failed to import {src} to staging path {target}: {exc}") from exc
            if mode == "copy":
                copy_count += 1

        if copy_count:
            warning = (
                f"{copy_count} file(s) were copied because hardlinking failed, likely due to a cross-filesystem mount."
            )
            warnings.append(warning)
            self.db.add_event(job_id, "warning", warning)

        self._publish_staged_import(staging_destination, destination)
        nudge_library_watchers(destination, settings)
        self.db.add_event(job_id, "info", f"Published import to {destination}")

        scan_warning = await self._trigger_scan(job_id, settings)
        if scan_warning:
            warnings.append(scan_warning)

        self.db.update_job(
            job_id,
            status="review" if needs_review else "completed",
            canonical_author=metadata.get("author"),
            book_title=metadata.get("title"),
            author_match=author_match,
            match_score=match_score,
            destination_path=str(destination),
            file_count=len(files),
            needs_review=needs_review,
            warnings=warnings,
            error=None,
        )
        if needs_review:
            self.db.add_event(job_id, "warning", "Import staged for manual review")
        else:
            self.db.add_event(job_id, "info", "Import complete")

    async def _complete_ebook_import(
        self,
        job_id: int,
        torrent: dict[str, Any],
        result: dict[str, Any],
        settings: DeweySettings,
        qbit: QbitClient,
    ) -> None:
        source_root = resolve_source_root(torrent, settings.torrents_dir)
        files = await self._resolve_media_files(torrent, source_root, qbit, collect_ebook_files)
        if not files:
            raise RuntimeError(f"No ebook files were found under {source_root}")

        self.db.update_job(job_id, download_path=str(source_root))
        self.db.add_event(job_id, "info", f"Found {len(files)} ebook file(s)")

        author, title = self._ebook_author_title(result, torrent)

        if settings.ebook_folder_layout == "flat":
            published_path = self._publish_ebook_flat(job_id, files, settings)
        else:
            published_path = self._publish_ebook_subfolder(job_id, files, source_root, author, title, settings)

        nudge_library_watchers(published_path, settings, root=settings.ebooks_dir)
        self.db.add_event(job_id, "info", f"Published ebook import to {published_path}")

        self.db.update_job(
            job_id,
            status="completed",
            canonical_author=author,
            book_title=title,
            destination_path=str(published_path),
            file_count=len(files),
            needs_review=False,
            warnings=[],
            error=None,
        )
        self.db.add_event(job_id, "info", "Ebook import complete")

    def _publish_ebook_flat(self, job_id: int, files: list[Path], settings: DeweySettings) -> Path:
        destination_dir = settings.ebooks_dir
        destination_dir.mkdir(parents=True, exist_ok=True)
        self.db.add_event(job_id, "info", f"Copying ebook file(s) into {destination_dir}")
        for src in files:
            target = destination_dir / src.name
            try:
                link_or_copy(src, target, prefer_hardlink=False)
            except OSError as exc:
                raise RuntimeError(f"Failed to copy {src} to {target}: {exc}") from exc
        return destination_dir

    def _publish_ebook_subfolder(
        self,
        job_id: int,
        files: list[Path],
        source_root: Path,
        author: str | None,
        title: str | None,
        settings: DeweySettings,
    ) -> Path:
        destination = unique_destination(self._ebook_folder(settings, author, title))
        staging_destination = self._ebook_staging_destination(job_id, destination, settings)
        if staging_destination.exists():
            shutil.rmtree(staging_destination)
        staging_destination.mkdir(parents=True, exist_ok=True)
        self.db.add_event(job_id, "info", f"Copying ebook file(s) into staging for {destination}")

        source_base = source_root if source_root.is_dir() else source_root.parent
        for src in files:
            try:
                relative = src.relative_to(source_base)
            except ValueError:
                relative = Path(src.name)
            target = staging_destination / relative
            try:
                link_or_copy(src, target, prefer_hardlink=False)
            except OSError as exc:
                raise RuntimeError(f"Failed to copy {src} to staging path {target}: {exc}") from exc

        self._publish_staged_import(staging_destination, destination)
        return destination

    def _ebook_author_title(self, result: dict[str, Any], torrent: dict[str, Any]) -> tuple[str | None, str | None]:
        release_title = result.get("title") or str(torrent.get("name") or "")
        parsed = parse_release_name(release_title, include_series_in_title=False)
        author = _metadata_text(result.get("author")) or parsed.author
        title = parsed.title or clean_release_text(release_title) or release_title or "Unknown Book"
        return author, title

    def _ebook_folder(self, settings: DeweySettings, author: str | None, title: str | None) -> Path:
        book_folder = safe_path_component(str(title or ""), fallback="Unknown Book")
        if author:
            author_folder = safe_path_component(str(author), fallback="Unknown Author")
            return settings.ebooks_dir / author_folder / book_folder
        return settings.ebooks_dir / book_folder

    def _ebook_staging_destination(self, job_id: int, destination: Path, settings: DeweySettings) -> Path:
        name = safe_path_component(destination.name, fallback="ebook")
        return settings.ebooks_dir / ".dewey-staging" / f"job-{job_id}-{name}"

    def _staging_destination(self, job_id: int, destination: Path, settings: DeweySettings) -> Path:
        name = safe_path_component(destination.name, fallback="audiobook")
        return settings.torrents_dir / ".dewey-staging" / f"job-{job_id}-{name}"

    def _publish_staged_import(self, staging_destination: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            staging_destination.rename(destination)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to publish staged import {staging_destination} to {destination}: {exc}"
            ) from exc

    async def _resolve_media_files(
        self,
        torrent: dict[str, Any],
        source_root: Path,
        qbit: QbitClient,
        collector: Callable[[Path], list[Path]],
    ) -> list[Path]:
        torrent_hash = torrent.get("hash")
        files: list[Path] = []
        save_path = Path(str(torrent.get("save_path") or source_root))

        if torrent_hash:
            try:
                for file_info in await qbit.torrent_files(str(torrent_hash)):
                    name = file_info.get("name")
                    if not name:
                        continue
                    candidate = Path(str(name))
                    if not candidate.is_absolute():
                        candidate = save_path / candidate
                    if candidate.exists():
                        files.extend(collector(candidate))
            except Exception:
                files = []

        if files:
            return sorted(set(files))
        return collector(source_root)

    async def _resolve_metadata(
        self,
        result: dict[str, Any],
        settings: DeweySettings,
    ) -> tuple[dict[str, Any], str | None]:
        release_title = result.get("title") or ""
        parsed = parse_release_name(
            release_title,
            include_series_in_title=settings.include_series_in_book_folder,
        )
        author_hint = _metadata_text(result.get("author")) or parsed.author
        lookup_title, _, _ = _title_candidate(
            release_title,
            author_hint,
            include_series_in_title=False,
        )
        fallback_title, parsed_series, parsed_confidence = _title_candidate(
            release_title,
            author_hint,
            include_series_in_title=settings.include_series_in_book_folder,
        )
        series = _metadata_text(result.get("series")) or parsed_series
        narrator = _metadata_text(result.get("narrator"))
        fallback_title = _apply_series_to_title(
            fallback_title,
            series,
            settings.include_series_in_book_folder,
        )

        warning: str | None = None
        metadata_result: MetadataResult | None = None
        try:
            metadata_result = await MetadataClient(settings).lookup(lookup_title or release_title, author_hint)
        except Exception as exc:  # noqa: BLE001 - metadata failure should not block fallback import.
            warning = f"Metadata lookup failed; falling back to torrent name parsing: {exc}"

        if metadata_result and metadata_result.score >= settings.metadata_confidence_threshold:
            resolved_title = _apply_series_to_title(
                metadata_result.title,
                series,
                settings.include_series_in_book_folder,
            )
            return (
                {
                    "author": metadata_result.author,
                    "title": resolved_title,
                    "series": series,
                    "narrator": narrator,
                    "confidence": metadata_result.score,
                    "source": metadata_result.provider,
                },
                warning,
            )

        if metadata_result:
            warning = (
                f"Metadata match for {metadata_result.title} by {metadata_result.author} was below threshold "
                f"({metadata_result.score:.0f}); using torrent metadata instead."
            )
        elif warning is None:
            warning = "No confident metadata match found; using torrent metadata instead."

        author = author_hint
        title = fallback_title or release_title
        source = "torrent-metadata" if result.get("author") else "torrent-name"
        confidence = parsed_confidence if author and title else 35
        if result.get("author") and title:
            confidence = max(confidence, 78)
        return (
            {
                "author": author,
                "title": title,
                "series": series,
                "narrator": narrator,
                "confidence": confidence,
                "source": source,
            },
            warning,
        )

    def _metadata_summary(self, metadata: dict[str, Any]) -> str | None:
        author = metadata.get("author") or "unknown author"
        title = metadata.get("title") or "unknown title"
        source = metadata.get("source") or "unknown source"
        confidence = metadata.get("confidence")
        if confidence is None:
            return f"Metadata resolved from {source}: {author} / {title}"
        return f"Metadata resolved from {source}: {author} / {title} (confidence {float(confidence):.0f})"

    def _metadata_review_reason(self, metadata: dict[str, Any], settings: DeweySettings) -> str | None:
        missing = []
        if not metadata.get("author"):
            missing.append("author")
        if not metadata.get("title"):
            missing.append("title")
        if missing:
            return f"Manual review needed because metadata is missing {', '.join(missing)}."
        confidence = float(metadata.get("confidence") or 0)
        if confidence < settings.fallback_confidence_threshold:
            return (
                f"Manual review needed because metadata confidence is {confidence:.0f}, "
                f"below the {settings.fallback_confidence_threshold} threshold."
            )
        return None

    def _destination_for(
        self,
        *,
        metadata: dict[str, Any],
        torrent_title: str,
        settings: DeweySettings,
    ) -> tuple[Path, bool, str | None, float | None]:
        author = metadata.get("author")
        title = metadata.get("title")
        confidence = float(metadata.get("confidence") or 0)
        needs_review = not author or not title or confidence < settings.fallback_confidence_threshold

        if needs_review:
            folder = safe_path_component(torrent_title, fallback="Unknown Audiobook")
            return settings.audiobooks_dir / settings.unsorted_folder / folder, True, None, None

        author_folder, score = self._match_author_folder(str(author), settings)
        book_folder = safe_path_component(str(title), fallback="Unknown Book")
        return author_folder / book_folder, False, author_folder.name, score

    def _match_author_folder(self, author: str, settings: DeweySettings) -> tuple[Path, float | None]:
        settings.audiobooks_dir.mkdir(parents=True, exist_ok=True)
        existing = [
            path.name
            for path in settings.audiobooks_dir.iterdir()
            if path.is_dir() and path.name != settings.unsorted_folder
        ]
        if existing:
            match = process.extractOne(author, existing, scorer=fuzz.WRatio)
            if match and float(match[1]) >= settings.author_match_threshold:
                return settings.audiobooks_dir / str(match[0]), float(match[1])
        return settings.audiobooks_dir / safe_path_component(author, fallback="Unknown Author"), None

    async def _trigger_scan(self, job_id: int, settings: DeweySettings) -> str | None:
        if not settings.audiobookshelf_scan_enabled:
            self.db.add_event(job_id, "info", "Audiobookshelf scan skipped; scan integration is disabled")
            return None

        client = AudiobookshelfClient(settings)
        if not client.configured:
            warning = "Audiobookshelf scan skipped because URL, API key, or library ID is not configured."
            self.db.add_event(job_id, "warning", warning)
            return warning

        self.db.update_job(job_id, status="scanning")
        self.db.add_event(job_id, "info", "Triggering Audiobookshelf library scan")
        try:
            await client.scan_library()
        except Exception as exc:  # noqa: BLE001 - files are already imported; keep the job completed with a warning.
            warning = f"Audiobookshelf scan request failed: {exc}"
            self.db.add_event(job_id, "warning", warning)
            return warning

        self.db.add_event(job_id, "info", "Audiobookshelf scan requested")
        return None
