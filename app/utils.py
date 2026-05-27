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


def collect_audio_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if is_audio_file(root) else []
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and is_audio_file(path):
            parts = {part.lower() for part in path.parts}
            if "sample" not in parts and "samples" not in parts:
                files.append(path)
    return sorted(files)


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


def link_or_copy(src: Path, dst: Path) -> tuple[str, Path]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst = unique_destination(dst)
    try:
        os.link(src, dst)
        return "hardlink", dst
    except OSError as link_error:
        try:
            shutil.copyfile(src, dst)
            try:
                shutil.copymode(src, dst)
            except OSError:
                pass
        except OSError as copy_error:
            raise OSError(
                f"Failed to hardlink or copy {src} to {dst}; "
                f"hardlink failed with {link_error}; copy failed with {copy_error}"
            ) from copy_error
        return "copy", dst
