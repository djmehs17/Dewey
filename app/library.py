from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from rapidfuzz import fuzz

from .models import SearchResult
from .settings import DeweySettings
from .utils import parse_release_name, safe_path_component, unique_destination


def find_library_matches(
    result: SearchResult,
    settings: DeweySettings,
    limit: int = 3,
) -> list[str]:
    root = settings.audiobooks_dir
    if not root.exists():
        return []

    author, title = _author_title(result)
    if not title:
        return []

    matches: list[tuple[float, Path]] = []
    for author_dir in root.iterdir():
        if not author_dir.is_dir() or author_dir.name == settings.unsorted_folder:
            continue
        author_score = _score(author, author_dir.name) if author else 100.0
        if author and author_score < 70:
            continue
        for book_dir in author_dir.iterdir():
            if not book_dir.is_dir():
                continue
            title_score = max(
                _score(title, book_dir.name),
                fuzz.token_set_ratio(_norm(title), _norm(book_dir.name)),
            )
            combined = (
                title_score
                if not author
                else (title_score * 0.76) + (author_score * 0.24)
            )
            if combined >= 86:
                matches.append((combined, book_dir))

    matches.sort(key=lambda item: item[0], reverse=True)
    return [str(path) for _, path in matches[:limit]]


def review_destination(settings: DeweySettings, author: str, title: str) -> Path:
    return (
        settings.audiobooks_dir
        / safe_path_component(author, fallback="Unknown Author")
        / safe_path_component(title, fallback="Unknown Book")
    )


def move_review_import(current: Path, destination: Path, settings: DeweySettings) -> Path:
    root = settings.audiobooks_dir.resolve()
    current = current.resolve()
    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)

    if not current.exists():
        raise FileNotFoundError(f"Review folder no longer exists: {current}")
    if not current.is_dir():
        raise ValueError(f"Review path is not a folder: {current}")
    if not current.is_relative_to(root):
        raise ValueError(f"Review path is outside the audiobook library: {current}")
    if current == destination.resolve():
        nudge_library_watchers(current, settings)
        return current
    target = unique_destination(destination)
    if not target.parent.resolve().is_relative_to(root):
        raise ValueError(f"Review destination is outside the audiobook library: {target}")

    try:
        current.rename(target)
    except OSError:
        shutil.move(str(current), str(target))
    nudge_library_watchers(target, settings)
    return target


def nudge_library_watchers(destination: Path, settings: DeweySettings, root: Path | None = None) -> None:
    library_root = root or settings.audiobooks_dir
    for path in (destination, destination.parent, library_root):
        try:
            os.utime(path, None)
        except OSError:
            continue


def _author_title(result: SearchResult) -> tuple[str | None, str | None]:
    parsed = parse_release_name(result.title or "")
    author = _first_person(result.author) or parsed.author
    title = parsed.title or result.title
    return author, title


def _first_person(value: str | None) -> str | None:
    if not value:
        return None
    return next(
        (part.strip() for part in re.split(r",|;|&|\band\b", value) if part.strip()),
        None,
    )


def _norm(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _score(left: str | None, right: str | None) -> float:
    return float(fuzz.WRatio(_norm(left), _norm(right)))
