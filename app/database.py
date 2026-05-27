from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ImportJob, JobEvent


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._lock, self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS import_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    query TEXT,
                    torrent_title TEXT NOT NULL,
                    source_indexer TEXT,
                    size INTEGER,
                    seeders INTEGER,
                    result_json TEXT NOT NULL,
                    torrent_url TEXT,
                    torrent_hash TEXT,
                    download_path TEXT,
                    canonical_author TEXT,
                    book_title TEXT,
                    author_match TEXT,
                    match_score REAL,
                    destination_path TEXT,
                    file_count INTEGER NOT NULL DEFAULT 0,
                    progress REAL NOT NULL DEFAULT 0,
                    needs_review INTEGER NOT NULL DEFAULT 0,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES import_jobs(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_import_jobs_status ON import_jobs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id)"
            )

    def create_job(self, *, query: str, result: dict[str, Any], category: str) -> int:
        created = now_iso()
        torrent_url = result.get("magnet_url") or result.get("download_url")
        with self._lock, self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO import_jobs (
                    created_at, updated_at, status, query, torrent_title,
                    source_indexer, size, seeders, result_json, torrent_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created,
                    created,
                    "queued",
                    query,
                    result.get("title") or "Untitled",
                    result.get("indexer"),
                    result.get("size"),
                    result.get("seeders"),
                    json.dumps(result),
                    torrent_url,
                ),
            )
            job_id = int(cursor.lastrowid)
        self.add_event(job_id, "info", f"Queued import using category '{category}'")
        return job_id

    def add_event(self, job_id: int, level: str, message: str) -> None:
        created = now_iso()
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO job_events (job_id, created_at, level, message) VALUES (?, ?, ?, ?)",
                (job_id, created, level, message),
            )
            conn.execute(
                "UPDATE import_jobs SET updated_at = ? WHERE id = ?",
                (created, job_id),
            )

    def update_job(self, job_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = now_iso()
        if "warnings" in fields:
            fields["warnings_json"] = json.dumps(fields.pop("warnings"))
        if "needs_review" in fields:
            fields["needs_review"] = 1 if fields["needs_review"] else 0
        columns = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [job_id]
        with self._lock, self.connect() as conn:
            conn.execute(f"UPDATE import_jobs SET {columns} WHERE id = ?", values)

    def get_job_row(self, job_id: int) -> sqlite3.Row | None:
        with self._lock, self.connect() as conn:
            return conn.execute(
                "SELECT * FROM import_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()

    def list_job_rows(self, limit: int = 50) -> list[sqlite3.Row]:
        with self._lock, self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM import_jobs ORDER BY datetime(created_at) DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )

    def delete_job(self, job_id: int) -> bool:
        with self._lock, self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM import_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM import_jobs WHERE id = ?", (job_id,))
            return True

    def delete_jobs_by_status(self, statuses: set[str]) -> int:
        if not statuses:
            return 0
        placeholders = ", ".join("?" for _ in statuses)
        values = sorted(statuses)
        with self._lock, self.connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM import_jobs WHERE status IN ({placeholders})",
                values,
            ).fetchall()
            job_ids = [int(row["id"]) for row in rows]
            if not job_ids:
                return 0
            job_placeholders = ", ".join("?" for _ in job_ids)
            conn.execute(f"DELETE FROM job_events WHERE job_id IN ({job_placeholders})", job_ids)
            conn.execute(f"DELETE FROM import_jobs WHERE id IN ({job_placeholders})", job_ids)
            return len(job_ids)

    def event_rows(self, job_id: int) -> list[sqlite3.Row]:
        with self._lock, self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM job_events WHERE job_id = ? ORDER BY id ASC",
                    (job_id,),
                ).fetchall()
            )

    def pending_job_ids(self) -> list[int]:
        with self._lock, self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM import_jobs
                WHERE status IN ('queued', 'downloading', 'importing', 'scanning')
                ORDER BY id ASC
                """
            ).fetchall()
            return [int(row["id"]) for row in rows]

    def to_job(self, row: sqlite3.Row, include_events: bool = False) -> ImportJob:
        warnings = json.loads(row["warnings_json"] or "[]")
        events = []
        if include_events:
            events = [self.to_event(event) for event in self.event_rows(int(row["id"]))]
        return ImportJob(
            id=int(row["id"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
            query=row["query"],
            torrent_title=row["torrent_title"],
            source_indexer=row["source_indexer"],
            size=row["size"],
            seeders=row["seeders"],
            torrent_hash=row["torrent_hash"],
            download_path=row["download_path"],
            canonical_author=row["canonical_author"],
            book_title=row["book_title"],
            author_match=row["author_match"],
            match_score=row["match_score"],
            destination_path=row["destination_path"],
            file_count=int(row["file_count"] or 0),
            progress=float(row["progress"] or 0),
            needs_review=bool(row["needs_review"]),
            warnings=warnings,
            error=row["error"],
            events=events,
        )

    @staticmethod
    def to_event(row: sqlite3.Row) -> JobEvent:
        return JobEvent(
            id=int(row["id"]),
            job_id=int(row["job_id"]),
            created_at=row["created_at"],
            level=row["level"],
            message=row["message"],
        )
