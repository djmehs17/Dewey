from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import generate_session_secret, issue_session, prepare_auth_settings_payload, verify_password, verify_session
from .database import Database
from .diagnostics import run_diagnostics
from .importer import ImportManager
from .integrations.mam import MamClient
from .library import find_library_matches, move_review_import, review_destination
from .models import (
    AuthLoginRequest,
    AuthStatusResponse,
    DiagnosticsResponse,
    ImportJob,
    ImportRequest,
    MamVipPurchaseRequest,
    MamVipPurchaseResponse,
    ReviewUpdateRequest,
    SearchResponse,
    SettingsResponse,
)
from .settings import DeweySettings, settings_manager


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
ACTIVE_IMPORT_STATUSES = {"queued", "downloading", "importing", "scanning"}
TERMINAL_IMPORT_STATUSES = {"completed", "error", "review"}
AUDIO_FORMAT_TOKENS = {"aac", "flac", "m4a", "m4b", "mp3", "ogg", "opus", "wav"}
EBOOK_FORMAT_TOKENS = {"azw", "azw3", "cb7", "cbr", "cbz", "epub", "mobi", "pdf"}
MIN_ACCOUNT_REFRESH_SECONDS = 60 * 60
AUTH_EXEMPT_PATHS = {"/login", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}

app = FastAPI(title="Dewey", version="0.1.0")
app.mount("/static", StaticFiles(directory=PROJECT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_DIR / "templates")
logger = logging.getLogger(__name__)


def configure_logging() -> None:
    settings = settings_manager.get()
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(settings.resolved_log_path, encoding="utf-8"),
        ],
    )


@app.on_event("startup")
async def startup() -> None:
    settings = settings_manager.load()
    configure_logging()
    db = Database(settings.resolved_database_path)
    db.init()
    app.state.db = db
    app.state.import_manager = ImportManager(db, settings_manager)
    app.state.import_manager.resume_pending()
    app.state.mam_account_refresh_task = asyncio.create_task(_mam_account_refresh_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "mam_account_refresh_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def get_db() -> Database:
    return app.state.db


@app.middleware("http")
async def require_dewey_auth(request: Request, call_next):
    settings = settings_manager.get()
    if not settings.auth_enabled or _is_auth_exempt(request.url.path):
        return await call_next(request)
    if _request_authenticated(request, settings):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Authentication required."}, status_code=401)
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    return RedirectResponse(f"/login?next={quote(next_path)}", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    settings = settings_manager.get()
    if not settings.auth_enabled:
        return RedirectResponse("/", status_code=303)
    if _request_authenticated(request, settings):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html")


@app.get("/api/auth/status", response_model=AuthStatusResponse)
async def auth_status(request: Request) -> AuthStatusResponse:
    settings = settings_manager.get()
    authenticated = not settings.auth_enabled or _request_authenticated(request, settings)
    return AuthStatusResponse(
        enabled=settings.auth_enabled,
        authenticated=authenticated,
        username=settings.auth_username if authenticated and settings.auth_enabled else None,
    )


@app.post("/api/auth/login", response_model=AuthStatusResponse)
async def auth_login(payload: AuthLoginRequest):
    settings = settings_manager.get()
    if not settings.auth_enabled:
        return AuthStatusResponse(enabled=False, authenticated=True)
    if not settings.auth_password_hash:
        raise HTTPException(status_code=503, detail="Dewey login is enabled but no password is configured.")
    if payload.username != settings.auth_username or not verify_password(payload.password, settings.auth_password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if not settings.auth_session_secret:
        settings = settings_manager.save({"auth_session_secret": generate_session_secret()})

    max_age = max(1, int(settings.auth_session_ttl_hours or 1)) * 60 * 60
    token = issue_session(settings.auth_username, settings.auth_session_secret, settings.auth_session_ttl_hours)
    response = JSONResponse(
        AuthStatusResponse(
            enabled=True,
            authenticated=True,
            username=settings.auth_username,
        ).model_dump()
    )
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    return response


@app.post("/api/auth/logout", response_model=AuthStatusResponse)
async def auth_logout():
    settings = settings_manager.get()
    response = JSONResponse(
        AuthStatusResponse(
            enabled=settings.auth_enabled,
            authenticated=False,
            username=None,
        ).model_dump()
    )
    response.delete_cookie(key=settings.auth_cookie_name)
    return response


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    return SettingsResponse(settings=settings_manager.get().public_dict())


@app.get("/api/diagnostics", response_model=DiagnosticsResponse)
async def diagnostics() -> DiagnosticsResponse:
    return await run_diagnostics(settings_manager.get(), get_db())


@app.put("/api/settings", response_model=SettingsResponse)
async def update_settings(payload: dict) -> SettingsResponse:
    try:
        updates = prepare_auth_settings_payload(payload, settings_manager.get())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = settings_manager.save(updates)
    configure_logging()
    return SettingsResponse(settings=settings.public_dict())


@app.post("/api/mam/account", response_model=SettingsResponse)
async def refresh_mam_account() -> SettingsResponse:
    try:
        settings = await _refresh_mam_account_settings()
    except Exception as exc:  # noqa: BLE001 - surface integration details to the personal UI.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SettingsResponse(settings=settings.public_dict())


@app.post("/api/mam/vip", response_model=MamVipPurchaseResponse)
async def buy_mam_vip(payload: MamVipPurchaseRequest) -> MamVipPurchaseResponse:
    try:
        purchase = await MamClient(settings_manager.get()).buy_vip(payload.duration)
        settings = await _refresh_mam_account_settings()
    except Exception as exc:  # noqa: BLE001 - surface integration details to the personal UI.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MamVipPurchaseResponse(settings=settings.public_dict(), purchase=purchase)


@app.get("/api/search", response_model=SearchResponse)
async def search(
    q: str,
    format: str = "",
    language: str = "",
    min_seeders: int | None = None,
    min_relevance: int | None = None,
    category: str = "",
    search_type: str = "",
) -> SearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query is required.")
    try:
        results = await MamClient(settings_manager.get()).search(
            query,
            format_filter=format,
            language_filter=language,
            min_seeders=min_seeders,
            min_relevance=min_relevance,
            category_filter=category,
            search_type=search_type,
        )
    except Exception as exc:  # noqa: BLE001 - surface integration details to the personal UI.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    settings = settings_manager.get()
    for result in results:
        result.library_matches = find_library_matches(result, settings)
    return SearchResponse(query=query, results=results)


@app.post("/api/imports", response_model=ImportJob)
async def create_import(payload: ImportRequest) -> ImportJob:
    settings = settings_manager.get()
    category = payload.category or settings.qbittorrent_category
    result = payload.result.model_dump()
    result["_category"] = category
    if not (result.get("magnet_url") or result.get("download_url")):
        raise HTTPException(status_code=400, detail="Selected result is missing a download URL.")
    if not _is_supported_audio_result(result):
        raise HTTPException(status_code=400, detail="Dewey currently imports audiobook formats only.")
    if _is_vip_result(result) and settings.mam_block_vip_when_inactive and settings.mam_vip_status != "active":
        try:
            settings = await _refresh_mam_account_settings()
        except Exception as exc:  # noqa: BLE001 - keep a clear import-facing error.
            raise HTTPException(
                status_code=409,
                detail=f"This torrent appears to require MyAnonamouse VIP, and Dewey could not refresh VIP status: {exc}",
            ) from exc
        if settings.mam_vip_status != "active":
            raise HTTPException(
                status_code=409,
                detail="This torrent appears to require MyAnonamouse VIP. Dewey refreshed your account status and VIP is not active.",
            )

    db = get_db()
    job_id = db.create_job(query=payload.query, result=result, category=category)
    library_matches = result.get("library_matches") or []
    if library_matches:
        db.add_event(
            job_id,
            "warning",
            f"Possible duplicate already in library: {library_matches[0]}",
        )
    app.state.import_manager.start(job_id)
    row = db.get_job_row(job_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Import job was not created.")
    return db.to_job(row, include_events=True)


@app.get("/api/imports", response_model=list[ImportJob])
async def list_imports(limit: int = 50) -> list[ImportJob]:
    db = get_db()
    return [db.to_job(row, include_events=False) for row in db.list_job_rows(limit=limit)]


@app.delete("/api/imports")
async def clear_imports(status: str = "terminal") -> dict[str, int]:
    db = get_db()
    if status == "terminal":
        statuses = TERMINAL_IMPORT_STATUSES
    else:
        statuses = {part.strip() for part in status.split(",") if part.strip()}
        if not statuses:
            raise HTTPException(status_code=400, detail="At least one status is required.")
        if statuses & ACTIVE_IMPORT_STATUSES:
            raise HTTPException(status_code=409, detail="Active imports cannot be cleared in bulk.")
    return {"deleted": db.delete_jobs_by_status(statuses)}


@app.get("/api/imports/{job_id}", response_model=ImportJob)
async def get_import(job_id: int) -> ImportJob:
    db = get_db()
    row = db.get_job_row(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Import job not found.")
    return db.to_job(row, include_events=True)


@app.delete("/api/imports/{job_id}")
async def delete_import(job_id: int) -> dict[str, bool]:
    db = get_db()
    row = db.get_job_row(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Import job not found.")
    if row["status"] in ACTIVE_IMPORT_STATUSES:
        raise HTTPException(status_code=409, detail="Active imports cannot be removed from history.")
    return {"deleted": db.delete_job(job_id)}


@app.post("/api/imports/{job_id}/retry", response_model=ImportJob)
async def retry_import(job_id: int) -> ImportJob:
    db = get_db()
    row = db.get_job_row(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Import job not found.")
    if row["status"] not in {"error", "review"}:
        raise HTTPException(status_code=409, detail="Only errored or review jobs can be retried.")
    db.update_job(job_id, status="queued", error=None, needs_review=False)
    db.add_event(job_id, "info", "Retry requested from UI")
    app.state.import_manager.start(job_id)
    updated = db.get_job_row(job_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Import job disappeared during retry.")
    return db.to_job(updated, include_events=True)


@app.post("/api/imports/{job_id}/review", response_model=ImportJob)
async def resolve_review_import(job_id: int, payload: ReviewUpdateRequest) -> ImportJob:
    db = get_db()
    row = db.get_job_row(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Import job not found.")
    if row["status"] != "review" and not bool(row["needs_review"]):
        raise HTTPException(status_code=409, detail="Only imports awaiting manual review can be resolved.")

    author = payload.author.strip()
    title = payload.title.strip()
    if not author or not title:
        raise HTTPException(status_code=400, detail="Author and title are required.")

    settings = settings_manager.get()
    destination = review_destination(settings, author, title)
    current_path = row["destination_path"]
    if current_path:
        try:
            destination = move_review_import(Path(current_path), destination, settings)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        db.add_event(job_id, "info", f"Moved reviewed import to {destination}")

    warnings = db.to_job(row).warnings
    scan_warning = await app.state.import_manager._trigger_scan(job_id, settings)
    if scan_warning and scan_warning not in warnings:
        warnings.append(scan_warning)

    db.update_job(
        job_id,
        status="completed",
        canonical_author=author,
        book_title=title,
        author_match=destination.parent.name,
        match_score=100.0,
        destination_path=str(destination),
        progress=1,
        needs_review=False,
        warnings=warnings,
        error=None,
    )
    db.add_event(job_id, "info", "Manual review resolved")
    updated = db.get_job_row(job_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Import job disappeared during review.")
    return db.to_job(updated, include_events=True)


def _is_supported_audio_result(result: dict[str, Any]) -> bool:
    format_tokens = set(re.findall(r"[a-z0-9]+", str(result.get("format") or "").lower()))
    if format_tokens & EBOOK_FORMAT_TOKENS:
        return False
    if format_tokens & AUDIO_FORMAT_TOKENS:
        return True

    values = [
        result.get("category"),
        result.get("title"),
        result.get("description"),
        " ".join(result.get("tags") or []),
    ]
    tokens = {
        token
        for value in values
        if value
        for token in re.findall(r"[a-z0-9]+", str(value).lower())
    }
    if tokens & AUDIO_FORMAT_TOKENS or any(token in {"audio", "audiobook", "audiobooks"} for token in tokens):
        return True
    if tokens & EBOOK_FORMAT_TOKENS:
        return False
    return True


def _is_vip_result(result: dict[str, Any]) -> bool:
    if result.get("vip_only") is True:
        return True
    flags = {str(flag).strip().lower() for flag in result.get("flags") or []}
    if "vip" in flags:
        return True
    values = [
        result.get("category"),
        result.get("title"),
        result.get("description"),
        " ".join(result.get("tags") or []),
    ]
    text = " ".join(str(value).lower() for value in values if value)
    return bool(re.search(r"(^|[^a-z0-9])vip([^a-z0-9]|$)", text))


def _is_auth_exempt(path: str) -> bool:
    return path in AUTH_EXEMPT_PATHS or path.startswith("/static/")


def _request_authenticated(request: Request, settings: DeweySettings) -> bool:
    return verify_session(
        request.cookies.get(settings.auth_cookie_name),
        username=settings.auth_username,
        secret=settings.auth_session_secret,
    )


async def _refresh_mam_account_settings() -> DeweySettings:
    status = await MamClient(settings_manager.get()).account_status()
    updates: dict[str, Any] = {
        "mam_vip_status": status.vip_status,
        "mam_account_class": status.class_name or "",
        "mam_vip_until": status.vip_until or "",
        "mam_account_last_refresh": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if status.bonus_points is not None:
        updates["mam_bonus_points"] = status.bonus_points
    if status.freeleech_wedges is not None:
        updates["mam_freeleech_wedges"] = status.freeleech_wedges
    return settings_manager.save(updates)


async def _mam_account_refresh_loop() -> None:
    while True:
        settings = settings_manager.get()
        if settings.mam_account_auto_refresh_enabled and settings.mam_id:
            try:
                await _refresh_mam_account_settings()
                logger.info("Refreshed MyAnonamouse account status")
            except Exception as exc:  # noqa: BLE001 - background refresh should not stop Dewey.
                logger.warning("MyAnonamouse account status refresh failed: %s", exc)
        await asyncio.sleep(_mam_account_refresh_interval_seconds(settings_manager.get()))


def _mam_account_refresh_interval_seconds(settings: DeweySettings) -> int:
    try:
        raw_hours = settings.mam_account_refresh_interval_hours
        hours = 8 if raw_hours is None else int(raw_hours)
    except (TypeError, ValueError):
        hours = 8
    return max(MIN_ACCOUNT_REFRESH_SECONDS, hours * 60 * 60)
