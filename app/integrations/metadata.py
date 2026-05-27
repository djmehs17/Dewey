from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from rapidfuzz import fuzz

from ..settings import DeweySettings
from ..utils import clean_release_text


@dataclass(frozen=True)
class MetadataResult:
    author: str
    title: str
    score: float
    provider: str


class MetadataClient:
    def __init__(self, settings: DeweySettings):
        self.settings = settings

    async def lookup(self, title: str, author: str | None = None) -> MetadataResult | None:
        if self.settings.metadata_provider.lower() != "openlibrary":
            return None
        return await self._lookup_openlibrary(title, author)

    async def _lookup_openlibrary(self, title: str, author: str | None = None) -> MetadataResult | None:
        if not title:
            return None

        params = {
            "title": clean_release_text(title),
            "fields": "key,title,author_name,first_publish_year",
            "limit": "8",
        }
        if author:
            params["author"] = clean_release_text(author)
        headers = {"User-Agent": self.settings.openlibrary_user_agent}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{self.settings.openlibrary_url}/search.json",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()

        docs = payload.get("docs") or []
        best: MetadataResult | None = None
        query_title = clean_release_text(title).lower()
        author_hint = clean_release_text(author or "").lower()
        for doc in docs:
            doc_title = doc.get("title")
            authors = doc.get("author_name") or []
            if not doc_title or not authors:
                continue
            score = self._score_candidate(query_title, author_hint, str(doc_title), [str(item) for item in authors])
            if best is None or score > best.score:
                best = MetadataResult(
                    author=str(authors[0]),
                    title=str(doc_title),
                    score=float(score),
                    provider="openlibrary",
                )
        return best

    @staticmethod
    def _score_candidate(
        query_title: str,
        author_hint: str,
        doc_title: str,
        authors: list[str],
    ) -> float:
        title_score = fuzz.WRatio(query_title, clean_release_text(doc_title).lower())
        if not author_hint:
            return float(title_score)
        author_score = max(
            (fuzz.WRatio(author_hint, clean_release_text(author).lower()) for author in authors),
            default=0,
        )
        return float((title_score * 0.75) + (author_score * 0.25))
