from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import qbittorrentapi
from rapidfuzz import fuzz

from ..settings import DeweySettings


COMPLETE_STATES = {
    "uploading",
    "stalledUP",
    "pausedUP",
    "queuedUP",
    "checkingUP",
    "forcedUP",
    "moving",
}


class QbitClient:
    def __init__(self, settings: DeweySettings):
        self.settings = settings

    async def add_torrent(self, url: str, category: str) -> None:
        await asyncio.to_thread(self._add_torrent_sync, url, category)

    async def add_torrent_file(self, torrent: bytes, filename: str, category: str) -> None:
        await asyncio.to_thread(self._add_torrent_file_sync, torrent, filename, category)

    async def find_torrent(self, *, category: str, title: str, expected_hash: str | None) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._find_torrent_sync, category, title, expected_hash)

    async def torrent_files(self, torrent_hash: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._torrent_files_sync, torrent_hash)

    def _client(self) -> qbittorrentapi.Client:
        if not self.settings.qbittorrent_url:
            raise RuntimeError("qBittorrent URL is required.")
        client = qbittorrentapi.Client(
            host=self.settings.qbittorrent_url,
            username=self.settings.qbittorrent_username or None,
            password=self.settings.qbittorrent_password or None,
            REQUESTS_ARGS={"timeout": 30},
        )
        if self.settings.qbittorrent_username or self.settings.qbittorrent_password:
            client.auth_log_in()
        return client

    def _add_torrent_sync(self, url: str, category: str) -> None:
        client = self._client()
        self._ensure_category(client, category)

        kwargs: dict[str, Any] = {"urls": url, "category": category}
        if self.settings.qbittorrent_save_path:
            kwargs["save_path"] = self.settings.qbittorrent_save_path
        client.torrents_add(**kwargs)

    def _add_torrent_file_sync(self, torrent: bytes, filename: str, category: str) -> None:
        client = self._client()
        self._ensure_category(client, category)

        kwargs: dict[str, Any] = {
            "torrent_files": {filename: torrent},
            "category": category,
        }
        if self.settings.qbittorrent_save_path:
            kwargs["save_path"] = self.settings.qbittorrent_save_path
        client.torrents_add(**kwargs)

    def _ensure_category(self, client: qbittorrentapi.Client, category: str) -> None:
        if not self.settings.ensure_qbittorrent_category or not category:
            return
        categories = client.torrents_categories()
        if category not in categories:
            client.torrents_create_category(name=category)

    def _find_torrent_sync(self, category: str, title: str, expected_hash: str | None) -> dict[str, Any] | None:
        client = self._client()
        torrents = client.torrents_info(category=category) if category else client.torrents_info()
        normalized_hash = expected_hash.lower() if expected_hash else None
        best: tuple[float, dict[str, Any]] | None = None

        for torrent in torrents:
            data = self._torrent_to_dict(torrent)
            torrent_hash = str(data.get("hash") or "").lower()
            if normalized_hash and torrent_hash == normalized_hash:
                return data

            name = str(data.get("name") or "")
            score = fuzz.WRatio(title.lower(), name.lower())
            added_bonus = min(float(data.get("added_on") or 0) / 10_000_000_000, 1.0)
            rank = score + added_bonus
            if score >= 70 and (best is None or rank > best[0]):
                best = (rank, data)

        return best[1] if best else None

    def _torrent_files_sync(self, torrent_hash: str) -> list[dict[str, Any]]:
        client = self._client()
        files: list[dict[str, Any]] = []
        for file_info in client.torrents_files(torrent_hash=torrent_hash):
            if isinstance(file_info, dict):
                files.append(dict(file_info))
                continue
            files.append(
                {
                    "name": getattr(file_info, "name", None),
                    "size": getattr(file_info, "size", None),
                    "progress": getattr(file_info, "progress", None),
                    "priority": getattr(file_info, "priority", None),
                    "is_seed": getattr(file_info, "is_seed", None),
                }
            )
        return files

    @staticmethod
    def _torrent_to_dict(torrent: Any) -> dict[str, Any]:
        if isinstance(torrent, dict):
            return dict(torrent)
        data: dict[str, Any] = {}
        for key in (
            "hash",
            "name",
            "state",
            "progress",
            "amount_left",
            "save_path",
            "content_path",
            "download_path",
            "category",
            "added_on",
            "total_size",
        ):
            data[key] = getattr(torrent, key, None)
        return data


def hash_from_magnet(url: str | None) -> str | None:
    if not url or not url.startswith("magnet:"):
        return None
    parsed = urlparse(url)
    xt_values = parse_qs(parsed.query).get("xt") or []
    for value in xt_values:
        match = re.search(r"btih:([a-fA-F0-9]{40}|[A-Z2-7]{32})", value)
        if match:
            return match.group(1).lower()
    return None


def is_complete(torrent: dict[str, Any]) -> bool:
    progress = float(torrent.get("progress") or 0)
    amount_left = torrent.get("amount_left")
    state = str(torrent.get("state") or "")
    no_bytes_left = amount_left is not None and int(amount_left) == 0
    return progress >= 0.999 or no_bytes_left or state in COMPLETE_STATES


def resolve_source_root(torrent: dict[str, Any], fallback_torrents_dir: Path) -> Path:
    content_path = torrent.get("content_path")
    if content_path:
        return Path(str(content_path))
    save_path = Path(str(torrent.get("save_path") or fallback_torrents_dir))
    name = str(torrent.get("name") or "")
    candidate = save_path / name if name else save_path
    return candidate if candidate.exists() else save_path
