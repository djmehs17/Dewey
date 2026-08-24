from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


AUDIO_EXTENSIONS = {
    ".aac",
    ".aiff",
    ".alac",
    ".ape",
    ".flac",
    ".m4a",
    ".m4b",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}

EBOOK_EXTENSIONS = {
    ".azw",
    ".azw3",
    ".azw4",
    ".cb7",
    ".cbr",
    ".cbz",
    ".djvu",
    ".epub",
    ".fb2",
    ".kfx",
    ".lit",
    ".mobi",
    ".pdb",
    ".pdf",
    ".prc",
}

NOISE_TOKEN_PATTERN = re.compile(
    r"\b(?:"
    r"audiobook|audible|unabridged|abridged|retail|"
    r"mp3|m4a|m4b|flac|aac|ogg|opus|wav|"
    r"\d{2,4}\s?kbps"
    r")\b",
    flags=re.I,
)


@dataclass(frozen=True)
class ParsedRelease:
    author: str | None
    title: str | None
    series: str | None
    confidence: int


def clean_release_text(value: str) -> str:
    value = re.sub(r"\[[^\]]+\]|\([^\)]*(?:kbps|audiobook|mp3|m4b|flac|narrat|read by)[^\)]*\)", " ", value, flags=re.I)
    value = re.sub(r"\b(?:read|narrated)\s+by\s+.+$", " ", value, flags=re.I)
    value = re.sub(r"\.(mp3|m4b|m4a|flac|aac|ogg|opus|wav)$", "", value, flags=re.I)
    value = value.replace("_", " ")
    value = NOISE_TOKEN_PATTERN.sub(" ", value)
    value = re.sub(r"\(\s*\)|\[\s*\]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .-_")


def parse_release_name(name: str, include_series_in_title: bool = False) -> ParsedRelease:
    cleaned = clean_release_text(name)
    parts = [part.strip() for part in re.split(r"\s+-\s+", cleaned) if part.strip()]

    if len(parts) >= 3:
        author = parts[0]
        series = " - ".join(parts[1:-1])
        title = parts[-1]
        if include_series_in_title and series:
            title = f"{series} - {title}"
        return ParsedRelease(author=author, title=title, series=series, confidence=88)

    if len(parts) == 2:
        return ParsedRelease(author=parts[0], title=parts[1], series=None, confidence=80)

    by = re.match(r"^(?P<title>.+?)\s+by\s+(?P<author>.+)$", cleaned, flags=re.I)
    if by:
        return ParsedRelease(
            author=by.group("author").strip(),
            title=by.group("title").strip(),
            series=None,
            confidence=78,
        )

    return ParsedRelease(author=None, title=cleaned or None, series=None, confidence=35)


def safe_path_component(value: str, fallback: str = "Unknown") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or fallback


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def is_ebook_file(path: Path) -> bool:
    return path.suffix.lower() in EBOOK_EXTENSIONS


def collect_media_files(root: Path, extensions: set[str]) -> list[Path]:
    matches = {ext.lower() for ext in extensions}
    if root.is_file():
        return [root] if root.suffix.lower() in matches else []
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in matches:
            parts = {part.lower() for part in path.parts}
            if "sample" not in parts and "samples" not in parts:
                files.append(path)
    return sorted(files)


def collect_audio_files(root: Path) -> list[Path]:
    return collect_media_files(root, AUDIO_EXTENSIONS)


def collect_ebook_files(root: Path) -> list[Path]:
    return collect_media_files(root, EBOOK_EXTENSIONS)


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Unable to find unique destination for {path}")


def link_or_copy(src: Path, dst: Path, *, prefer_hardlink: bool = True) -> tuple[str, Path]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst = unique_destination(dst)
    link_error: OSError | None = None
    if prefer_hardlink:
        try:
            os.link(src, dst)
            return "hardlink", dst
        except OSError as exc:
            link_error = exc
    try:
        shutil.copyfile(src, dst)
        try:
            shutil.copymode(src, dst)
        except OSError:
            pass
    except OSError as copy_error:
        if link_error is not None:
            raise OSError(
                f"Failed to hardlink or copy {src} to {dst}; "
                f"hardlink failed with {link_error}; copy failed with {copy_error}"
            ) from copy_error
        raise OSError(f"Failed to copy {src} to {dst}: {copy_error}") from copy_error
    return "copy", dst
