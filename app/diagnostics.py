from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .database import Database
from .integrations.mam import MamClient
from .integrations.qbit import QbitClient
from .models import DiagnosticCheck, DiagnosticsResponse
from .settings import DeweySettings


OK = "ok"
WARN = "warn"
ERROR = "error"
SKIPPED = "skipped"


async def run_diagnostics(settings: DeweySettings, db: Database) -> DiagnosticsResponse:
    checks = [
        _config_check(settings),
        _database_check(db),
        _path_check("audiobooks-path", "Audiobooks path", settings.audiobooks_dir),
        _path_check("torrents-path", "Torrents path", settings.torrents_dir),
        _path_check("staging-path", "Staging path", settings.torrents_dir / ".dewey-staging", create=True),
        await _qbit_check(settings),
        await _mam_check(settings),
        await _audiobookshelf_check(settings),
    ]
    return DiagnosticsResponse(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        overall_status=_overall_status(checks),
        checks=checks,
    )


def _overall_status(checks: list[DiagnosticCheck]) -> str:
    statuses = {check.status for check in checks}
    if ERROR in statuses:
        return ERROR
    if WARN in statuses:
        return WARN
    return OK


def _check(check_id: str, name: str, status: str, summary: str, *, detail: str | None = None, **values: Any) -> DiagnosticCheck:
    return DiagnosticCheck(
        id=check_id,
        name=name,
        status=status,
        summary=summary,
        detail=detail,
        values={key: value for key, value in values.items() if value is not None},
    )


def _config_check(settings: DeweySettings) -> DiagnosticCheck:
    missing = []
    if not settings.mam_id:
        missing.append("mam_id")
    if not settings.qbittorrent_url:
        missing.append("qBittorrent URL")
    if not settings.qbittorrent_category:
        missing.append("qBittorrent category")

    if missing:
        return _check(
            "configuration",
            "Configuration",
            WARN,
            "Some required settings are missing.",
            detail=", ".join(missing),
        )
    return _check("configuration", "Configuration", OK, "Required settings are present.")


def _database_check(db: Database) -> DiagnosticCheck:
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        return _check(
            "database",
            "Database",
            ERROR,
            "Dewey could not open the SQLite database.",
            detail=str(exc),
            path=str(db.path),
        )
    return _check("database", "Database", OK, "SQLite database is reachable.", path=str(db.path))


def _path_check(check_id: str, name: str, path: Path, *, create: bool = False) -> DiagnosticCheck:
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            return _check(check_id, name, ERROR, "Path does not exist.", path=str(path))
        if not path.is_dir():
            return _check(check_id, name, ERROR, "Path is not a directory.", path=str(path))

        probe = path / f".dewey-diagnostic-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return _check(
            check_id,
            name,
            ERROR,
            "Dewey cannot write to this path.",
            detail=str(exc),
            path=str(path),
        )
    return _check(check_id, name, OK, "Path exists and is writable.", path=str(path))


async def _qbit_check(settings: DeweySettings) -> DiagnosticCheck:
    if not settings.qbittorrent_url:
        return _check("qbittorrent", "qBittorrent", ERROR, "qBittorrent URL is not configured.")

    def check_sync() -> dict[str, Any]:
        client = QbitClient(settings)._client()
        categories = client.torrents_categories()
        category_names = set(categories.keys() if isinstance(categories, dict) else categories)
        return {
            "version": str(client.app.version),
            "category_exists": not settings.qbittorrent_category or settings.qbittorrent_category in category_names,
        }

    try:
        result = await asyncio.to_thread(check_sync)
    except Exception as exc:  # noqa: BLE001 - diagnostics should report integration failures plainly.
        return _check(
            "qbittorrent",
            "qBittorrent",
            ERROR,
            "Dewey could not connect to qBittorrent.",
            detail=str(exc),
            url=settings.qbittorrent_url,
        )

    if not result["category_exists"]:
        return _check(
            "qbittorrent",
            "qBittorrent",
            WARN,
            "qBittorrent is reachable, but the configured category is missing.",
            url=settings.qbittorrent_url,
            category=settings.qbittorrent_category,
            version=result["version"],
        )
    return _check(
        "qbittorrent",
        "qBittorrent",
        OK,
        "qBittorrent is reachable.",
        url=settings.qbittorrent_url,
        category=settings.qbittorrent_category,
        version=result["version"],
    )


async def _mam_check(settings: DeweySettings) -> DiagnosticCheck:
    if not settings.mam_id:
        return _check("mam", "MyAnonamouse", ERROR, "mam_id is not configured.")
    try:
        status = await MamClient(settings).account_status()
    except Exception as exc:  # noqa: BLE001 - diagnostics should report integration failures plainly.
        return _check(
            "mam",
            "MyAnonamouse",
            ERROR,
            "Dewey could not refresh MAM account status.",
            detail=str(exc),
            url=settings.mam_url,
        )
    return _check(
        "mam",
        "MyAnonamouse",
        OK,
        "MAM account status is reachable.",
        url=settings.mam_url,
        vip=status.vip_status,
        account_class=status.class_name,
        vip_until=status.vip_until,
    )


async def _audiobookshelf_check(settings: DeweySettings) -> DiagnosticCheck:
    if not settings.audiobookshelf_scan_enabled:
        return _check(
            "audiobookshelf",
            "Audiobookshelf scan",
            SKIPPED,
            "Scan integration is disabled.",
        )
    missing = []
    if not settings.audiobookshelf_url:
        missing.append("URL")
    if not settings.audiobookshelf_api_key:
        missing.append("API key")
    if not settings.audiobookshelf_library_id:
        missing.append("library ID")
    if missing:
        return _check(
            "audiobookshelf",
            "Audiobookshelf scan",
            ERROR,
            "Scan integration is enabled but incomplete.",
            detail=", ".join(missing),
        )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.audiobookshelf_url}/api/libraries/{settings.audiobookshelf_library_id}",
                headers={"Authorization": f"Bearer {settings.audiobookshelf_api_key}"},
            )
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - diagnostics should report integration failures plainly.
        return _check(
            "audiobookshelf",
            "Audiobookshelf scan",
            WARN,
            "Audiobookshelf scan is configured, but the library check failed.",
            detail=str(exc),
            url=settings.audiobookshelf_url,
            library_id=settings.audiobookshelf_library_id,
        )
    return _check(
        "audiobookshelf",
        "Audiobookshelf scan",
        OK,
        "Audiobookshelf library endpoint is reachable.",
        url=settings.audiobookshelf_url,
        library_id=settings.audiobookshelf_library_id,
    )
