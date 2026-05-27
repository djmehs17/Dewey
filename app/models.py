from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    id: str
    title: str
    author: str | None = None
    narrator: str | None = None
    series: str | None = None
    size: int | None = None
    seeders: int | None = None
    leechers: int | None = None
    snatches: int | None = None
    comments: int | None = None
    thanks: int | None = None
    file_count: int | None = None
    relevance: int | None = None
    format: str | None = None
    category: str | None = None
    language: str | None = None
    duration: str | None = None
    bitrate: str | None = None
    uploaded_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    vip_only: bool = False
    freeleech: bool = False
    fl_vip: bool = False
    personal_freeleech: bool = False
    my_snatched: bool = False
    category_id: int | None = None
    main_category_id: int | None = None
    indexer: str | None = None
    protocol: str | None = None
    provider: str | None = None
    torrent_id: str | None = None
    requires_dewey_download: bool = False
    download_url: str | None = None
    magnet_url: str | None = None
    info_url: str | None = None
    description: str | None = None
    library_matches: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class ImportRequest(BaseModel):
    query: str
    result: SearchResult
    category: str | None = None


class MamVipPurchaseRequest(BaseModel):
    duration: str = "4"


class MamVipPurchaseResponse(BaseModel):
    settings: dict[str, Any]
    purchase: dict[str, Any] = Field(default_factory=dict)


class ReviewUpdateRequest(BaseModel):
    author: str
    title: str


class JobEvent(BaseModel):
    id: int
    job_id: int
    created_at: str
    level: str
    message: str


class ImportJob(BaseModel):
    id: int
    created_at: str
    updated_at: str
    status: str
    query: str | None = None
    torrent_title: str
    source_indexer: str | None = None
    size: int | None = None
    seeders: int | None = None
    torrent_hash: str | None = None
    download_path: str | None = None
    canonical_author: str | None = None
    book_title: str | None = None
    author_match: str | None = None
    match_score: float | None = None
    destination_path: str | None = None
    file_count: int = 0
    progress: float = 0.0
    needs_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    events: list[JobEvent] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    settings: dict[str, Any]


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthStatusResponse(BaseModel):
    enabled: bool
    authenticated: bool
    username: str | None = None


class DiagnosticCheck(BaseModel):
    id: str
    name: str
    status: str
    summary: str
    detail: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class DiagnosticsResponse(BaseModel):
    generated_at: str
    overall_status: str
    checks: list[DiagnosticCheck]


class MamAccountStatus(BaseModel):
    vip_status: str = "unknown"
    class_name: str | None = None
    vip_until: str | None = None
    bonus_points: int | None = None
    freeleech_wedges: int | None = None
