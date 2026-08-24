from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SEARCH_PROFILES: list[dict[str, Any]] = [
    {
        "id": "m4b-english",
        "name": "M4B English",
        "format": "m4b",
        "language": "ENG",
        "min_seeders": 1,
        "min_relevance": 55,
        "search_type": "active",
        "category": "13",
    },
    {
        "id": "m4b-non-vip",
        "name": "M4B non-VIP",
        "format": "m4b",
        "language": "ENG",
        "min_seeders": 1,
        "min_relevance": 55,
        "search_type": "nVIP",
        "category": "13",
    },
    {
        "id": "freeleech-m4b",
        "name": "Freeleech M4B",
        "format": "m4b",
        "language": "ENG",
        "min_seeders": 0,
        "min_relevance": 50,
        "search_type": "fl",
        "category": "13",
    },
    {
        "id": "broad-audio",
        "name": "Broad audiobook",
        "format": "",
        "language": "ENG",
        "min_seeders": 0,
        "min_relevance": 45,
        "search_type": "active",
        "category": "13",
    },
]


class DeweySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DEWEY_",
        extra="ignore",
    )

    config_dir: Path = Path("/config")
    database_path: Path | None = None
    log_path: Path | None = None
    host: str = "0.0.0.0"
    port: int = 8686

    mam_url: str = "https://www.myanonamouse.net"
    mam_id: str = ""
    mam_audiobook_category: str = "13"
    mam_search_limit: int = 100
    mam_min_relevance: int = 45
    mam_min_seeders: int = 0
    mam_default_format: str = ""
    mam_default_language: str = ""
    mam_default_search_type: str = "all"
    mam_sort_type: str = "default"
    mam_update_seedbox_ip: bool = False
    mam_vip_status: str = "unknown"
    mam_block_vip_when_inactive: bool = True
    mam_vip_store_url: str = "https://www.myanonamouse.net/store.php"
    mam_account_class: str = ""
    mam_vip_until: str = ""
    mam_account_last_refresh: str = ""
    mam_account_auto_refresh_enabled: bool = True
    mam_account_refresh_interval_hours: int = 8
    mam_bonus_points: int | None = None
    mam_freeleech_wedges: int | None = None
    search_profiles: list[dict[str, Any]] = Field(
        default_factory=lambda: [dict(profile) for profile in DEFAULT_SEARCH_PROFILES]
    )

    qbittorrent_url: str = ""
    qbittorrent_username: str = ""
    qbittorrent_password: str = ""
    qbittorrent_category: str = "audiobooks"
    qbittorrent_save_path: str = ""
    ensure_qbittorrent_category: bool = True
    monitor_interval_seconds: int = 30

    audiobooks_dir: Path = Path("/data/audiobooks")
    torrents_dir: Path = Path("/data/torrents")
    unsorted_folder: str = "_unsorted"
    author_match_threshold: int = 85
    metadata_confidence_threshold: int = 74
    fallback_confidence_threshold: int = 65
    include_series_in_book_folder: bool = False

    ebooks_dir: Path = Path("/data/ebooks")
    ebook_folder_layout: str = "subfolder"
    ebook_search_category: str = "14"
    ebook_default_format: str = ""
    ebook_default_language: str = ""

    audiobookshelf_scan_enabled: bool = False
    audiobookshelf_url: str = ""
    audiobookshelf_api_key: str = ""
    audiobookshelf_library_id: str = ""
    audiobookshelf_force_scan: bool = False

    openlibrary_url: str = "https://openlibrary.org"
    openlibrary_user_agent: str = "Dewey/0.1 (+self-hosted audiobook importer)"
    metadata_provider: str = "openlibrary"

    auth_enabled: bool = False
    auth_username: str = "admin"
    auth_password_hash: str = ""
    auth_session_secret: str = ""
    auth_cookie_name: str = "dewey_session"
    auth_cookie_secure: bool = False
    auth_session_ttl_hours: int = 168

    log_level: str = "INFO"

    @field_validator("mam_url", "mam_vip_store_url", "qbittorrent_url", "audiobookshelf_url", "openlibrary_url")
    @classmethod
    def strip_trailing_slashes(cls, value: str) -> str:
        return value.rstrip("/") if value else value

    @field_validator("mam_vip_status")
    @classmethod
    def validate_vip_status(cls, value: str) -> str:
        normalized = (value or "unknown").strip().lower()
        return normalized if normalized in {"unknown", "active", "inactive"} else "unknown"

    @field_validator("ebook_folder_layout")
    @classmethod
    def validate_ebook_folder_layout(cls, value: str) -> str:
        normalized = (value or "subfolder").strip().lower()
        return normalized if normalized in {"subfolder", "flat"} else "subfolder"

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.config_dir / "dewey.sqlite3"

    @property
    def resolved_log_path(self) -> Path:
        return self.log_path or self.config_dir / "dewey.log"

    @classmethod
    def editable_fields(cls) -> set[str]:
        return {
            "mam_url",
            "mam_id",
            "mam_audiobook_category",
            "mam_search_limit",
            "mam_min_relevance",
            "mam_min_seeders",
            "mam_default_format",
            "mam_default_language",
            "mam_default_search_type",
            "mam_sort_type",
            "mam_update_seedbox_ip",
            "mam_vip_status",
            "mam_block_vip_when_inactive",
            "mam_vip_store_url",
            "mam_account_class",
            "mam_vip_until",
            "mam_account_last_refresh",
            "mam_account_auto_refresh_enabled",
            "mam_account_refresh_interval_hours",
            "mam_bonus_points",
            "mam_freeleech_wedges",
            "search_profiles",
            "qbittorrent_url",
            "qbittorrent_username",
            "qbittorrent_password",
            "qbittorrent_category",
            "qbittorrent_save_path",
            "ensure_qbittorrent_category",
            "monitor_interval_seconds",
            "audiobooks_dir",
            "torrents_dir",
            "unsorted_folder",
            "author_match_threshold",
            "metadata_confidence_threshold",
            "fallback_confidence_threshold",
            "include_series_in_book_folder",
            "ebooks_dir",
            "ebook_folder_layout",
            "ebook_search_category",
            "ebook_default_format",
            "ebook_default_language",
            "audiobookshelf_scan_enabled",
            "audiobookshelf_url",
            "audiobookshelf_api_key",
            "audiobookshelf_library_id",
            "audiobookshelf_force_scan",
            "openlibrary_url",
            "openlibrary_user_agent",
            "metadata_provider",
            "auth_enabled",
            "auth_username",
            "auth_password_hash",
            "auth_session_secret",
            "auth_cookie_name",
            "auth_cookie_secure",
            "auth_session_ttl_hours",
            "log_level",
        }

    def public_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["database_path"] = str(self.resolved_database_path)
        data["log_path"] = str(self.resolved_log_path)
        for secret_key in (
            "mam_id",
            "qbittorrent_password",
            "audiobookshelf_api_key",
            "auth_password_hash",
            "auth_session_secret",
        ):
            data[f"{secret_key}_configured"] = bool(getattr(self, secret_key, ""))
            data[secret_key] = ""
        data["auth_password_configured"] = bool(self.auth_password_hash)
        data["auth_password"] = ""
        return data


class SettingsManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings: DeweySettings | None = None

    def _settings_file(self, settings: DeweySettings) -> Path:
        return settings.config_dir / "settings.json"

    def load(self) -> DeweySettings:
        with self._lock:
            env_settings = DeweySettings()
            settings_file = self._settings_file(env_settings)
            if settings_file.exists():
                saved = json.loads(settings_file.read_text(encoding="utf-8"))
                allowed = {k: v for k, v in saved.items() if k in DeweySettings.editable_fields()}
                env_settings = DeweySettings.model_validate(
                    env_settings.model_dump() | allowed
                )
            self._settings = env_settings
            return env_settings

    def get(self) -> DeweySettings:
        with self._lock:
            return self._settings or self.load()

    def save(self, updates: dict[str, Any]) -> DeweySettings:
        with self._lock:
            current = self.get()
            allowed = {k: v for k, v in updates.items() if k in DeweySettings.editable_fields()}
            for secret_key in (
                "mam_id",
                "qbittorrent_password",
                "audiobookshelf_api_key",
                "auth_password_hash",
                "auth_session_secret",
            ):
                if allowed.get(secret_key) == "" and getattr(current, secret_key, ""):
                    allowed.pop(secret_key)
            updated = DeweySettings.model_validate(current.model_dump() | allowed)
            settings_file = self._settings_file(updated)
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                key: getattr(updated, key)
                for key in sorted(DeweySettings.editable_fields())
            }
            settings_file.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
            self._settings = updated
            return updated


settings_manager = SettingsManager()
