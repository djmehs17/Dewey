from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin

import httpx
from rapidfuzz import fuzz

from ..models import MamAccountStatus, SearchResult
from ..settings import DeweySettings
from ..utils import parse_release_name, safe_path_component


STOPWORDS = {
    "a",
    "an",
    "and",
    "book",
    "by",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "unabridged",
}

LANGUAGE_ALIASES = {
    "en": {"en", "eng", "english"},
    "eng": {"en", "eng", "english"},
    "english": {"en", "eng", "english"},
}

SEARCH_TYPES = {"all", "active", "inactive", "fl", "fl-VIP", "VIP", "nVIP", "nMeta"}
VIP_DURATIONS = {"4", "8", "12", "max"}


class MamClient:
    def __init__(self, settings: DeweySettings):
        self.settings = settings
        self.base_url = settings.mam_url.rstrip("/") + "/"

    async def search(
        self,
        query: str,
        format_filter: str = "",
        language_filter: str = "",
        min_seeders: int | None = None,
        min_relevance: int | None = None,
        category_filter: str = "",
        search_type: str = "",
    ) -> list[SearchResult]:
        if not self.settings.mam_id:
            raise RuntimeError("MyAnonamouse mam_id is required before searching.")

        if self.settings.mam_update_seedbox_ip:
            await self.update_seedbox_ip()

        format_filter = (format_filter or "").strip() or self.settings.mam_default_format
        language_filter = (language_filter or "").strip() or self.settings.mam_default_language
        seed_floor = max(0, int(self.settings.mam_min_seeders if min_seeders is None else min_seeders or 0))
        search_type = self._search_type(search_type or self.settings.mam_default_search_type)
        relevance_floor = max(
            0,
            min(int(self.settings.mam_min_relevance if min_relevance is None else min_relevance or 0), 100),
        )
        limit = max(5, min(int(self.settings.mam_search_limit or 100), 1000))
        search_text = self._significant_query(query)
        payload = self._search_payload(
            search_text,
            start=0,
            limit=limit,
            category_filter=category_filter,
            search_type=search_type,
        )

        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.post(
                urljoin(self.base_url, "tor/js/loadSearchJSONbasic.php"),
                cookies={"mam_id": self.settings.mam_id},
                json=payload,
                headers={"User-Agent": "Dewey/0.1"},
            )
            if response.status_code in {401, 403}:
                raise RuntimeError(
                    "MyAnonamouse rejected the request. Check mam_id and, if needed, enable the dynamic seedbox IP option in MAM and Dewey."
                )
            response.raise_for_status()
            data = response.json()

        if data.get("error"):
            return []
        rows = data.get("data")
        if not isinstance(rows, list):
            return []
        results = [self._normalize(item) for item in rows[:limit] if isinstance(item, dict)]
        for result in results:
            result.relevance = self._relevance(query, result)
        results = [result for result in results if self._format_matches(result, format_filter)]
        results = [result for result in results if self._language_matches(result, language_filter)]
        results = [result for result in results if (result.seeders or 0) >= seed_floor]
        filtered = [result for result in results if (result.relevance or 0) >= relevance_floor]
        return sorted(filtered, key=lambda result: self._sort_key(query, result), reverse=True)

    async def update_seedbox_ip(self) -> None:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(
                urljoin(self.base_url, "json/dynamicSeedbox.php"),
                cookies={"mam_id": self.settings.mam_id},
                headers={"User-Agent": "Dewey/0.1"},
            )
            if response.status_code in {401, 403}:
                raise RuntimeError("MyAnonamouse rejected the dynamic seedbox IP update. Check mam_id.")
            response.raise_for_status()

    async def account_status(self) -> MamAccountStatus:
        if not self.settings.mam_id:
            raise RuntimeError("MyAnonamouse mam_id is required before refreshing account status.")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(
                urljoin(self.base_url, "jsonLoad.php"),
                cookies={"mam_id": self.settings.mam_id},
                headers={"User-Agent": "Dewey/0.1"},
            )
            if response.status_code in {401, 403}:
                raise RuntimeError("MyAnonamouse rejected the account status request. Check mam_id.")
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("MyAnonamouse returned an unexpected account status response.")
        return self._parse_account_status(data)

    async def buy_vip(self, duration: str = "4") -> dict[str, Any]:
        duration = str(duration or "4")
        if duration not in VIP_DURATIONS:
            raise RuntimeError("VIP duration must be 4, 8, 12, or max.")
        if not self.settings.mam_id:
            raise RuntimeError("MyAnonamouse mam_id is required before buying VIP.")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.post(
                urljoin(self.base_url, "json/bonusBuy.php"),
                cookies={"mam_id": self.settings.mam_id},
                data={"spendtype": "VIP", "duration": duration},
                headers={"User-Agent": "Dewey/0.1"},
            )
            if response.status_code in {401, 403}:
                raise RuntimeError("MyAnonamouse rejected the VIP purchase request. Check mam_id.")
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("MyAnonamouse returned an unexpected VIP purchase response.") from exc
        if isinstance(data, dict) and data.get("Success") is False:
            raise RuntimeError(str(data.get("msg") or "MyAnonamouse VIP purchase failed."))
        if isinstance(data, dict) and data.get("success") is False:
            raise RuntimeError(str(data.get("msg") or data.get("message") or "MyAnonamouse VIP purchase failed."))
        return data if isinstance(data, dict) else {"response": data}

    async def download_torrent(self, result: dict[str, Any]) -> tuple[bytes, str]:
        torrent_id = result.get("torrent_id") or result.get("id") or result.get("tid")
        download_url = result.get("download_url")
        if not torrent_id and not download_url:
            raise RuntimeError("Selected MyAnonamouse result did not include a torrent ID or download URL.")
        if not self.settings.mam_id:
            raise RuntimeError("MyAnonamouse mam_id is required before downloading.")

        title = safe_path_component(str(result.get("title") or f"mam-{torrent_id}"), fallback=f"mam-{torrent_id}")
        filename = f"{title[:120]}.torrent"
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.get(
                urljoin(self.base_url, str(download_url or f"tor/download.php?tid={torrent_id}")),
                cookies={"mam_id": self.settings.mam_id},
                headers={"User-Agent": "Dewey/0.1"},
            )
            if response.status_code in {401, 403}:
                raise RuntimeError("MyAnonamouse rejected the torrent download. Check mam_id and seedbox IP settings.")
            response.raise_for_status()
            content = response.content

        if not content or not content.startswith(b"d") or b"announce" not in content[:4096]:
            raise RuntimeError("MyAnonamouse did not return a valid torrent file.")
        return content, filename

    def _search_payload(
        self,
        query: str,
        *,
        start: int,
        limit: int,
        category_filter: str = "",
        search_type: str = "all",
    ) -> dict[str, Any]:
        category = str((category_filter or "").strip() or self.settings.mam_audiobook_category or "13")
        main_cat: str | list[str] = [category] if category.isdigit() else category
        tor: dict[str, Any] = {
            "text": query,
            "srchIn": ["title", "author", "series", "narrator"],
            "searchType": search_type,
            "searchIn": "torrents",
            "main_cat": main_cat,
            "cat": ["0"],
            "startNumber": start,
            "perpage": limit,
        }
        if self.settings.mam_sort_type and self.settings.mam_sort_type != "default":
            tor["sortType"] = self.settings.mam_sort_type
        return {
            "text": query,
            "limit": limit,
            "dlLink": "",
            "isbn": "",
            "tor": tor,
        }

    def _normalize(self, item: dict[str, Any]) -> SearchResult:
        title = self._text(item.get("title") or item.get("name")) or "Untitled"
        parsed = parse_release_name(title)
        torrent_id = self._text(item.get("id") or item.get("tid") or item.get("torrent_id"))
        identity = torrent_id or item.get("guid") or title
        result_id = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:16]

        author = (
            self._names(item.get("author_info"))
            or self._names(item.get("authors"))
            or self._names(item.get("author"))
            or parsed.author
        )
        narrator = self._names(item.get("narrator_info") or item.get("narrators") or item.get("narrator"))
        series = self._names(item.get("series_info") or item.get("series"), include_position=True)
        category_id = self._int(item.get("category") or item.get("cat_id"))
        main_category_id = self._int(item.get("main_cat") or item.get("main_category"))
        category = self._text(item.get("catname") or item.get("cat") or item.get("cat_name") or item.get("category"))
        language = self._text(item.get("lang_code") or item.get("language") or item.get("lang"))
        tags = self._name_list(item.get("tags") or item.get("taglist") or item.get("tag_info"))
        flags = self._flags(item)
        vip_only = self._has_flag(flags, "VIP")
        freeleech = self._has_flag(flags, "Freeleech")
        fl_vip = self._truthy(item.get("fl_vip"))
        personal_freeleech = self._truthy(item.get("personal_freeleech"))
        my_snatched = self._truthy(item.get("my_snatched"))
        download_url = self._download_url(item)
        if not download_url and torrent_id:
            download_url = urljoin(self.base_url, f"tor/download.php?tid={torrent_id}")
        info_url = urljoin(self.base_url, f"t/{torrent_id}") if torrent_id else None

        return SearchResult(
            id=result_id,
            title=title,
            author=author,
            narrator=narrator,
            series=series or parsed.series,
            size=self._size(item.get("size") or item.get("size_bytes")),
            seeders=self._int(item.get("seeders") or item.get("seed") or item.get("seeds")),
            leechers=self._int(item.get("leechers") or item.get("leech") or item.get("peers")),
            snatches=self._int(
                item.get("times_completed") or item.get("snatched") or item.get("snatches") or item.get("downloads")
            ),
            comments=self._int(item.get("comments") or item.get("comment_count")),
            thanks=self._int(item.get("thanks") or item.get("thankyou") or item.get("thank_you")),
            file_count=self._int(item.get("file_count") or item.get("numfiles") or item.get("files")),
            format=self._text(item.get("filetype") or item.get("filetypes") or item.get("format") or item.get("type")),
            category=category,
            language=language,
            duration=self._text(item.get("duration") or item.get("runtime") or item.get("length")),
            bitrate=self._text(item.get("bitrate") or item.get("encoding")),
            uploaded_at=self._text(item.get("added") or item.get("date") or item.get("uploaded") or item.get("created_at")),
            tags=tags,
            flags=flags,
            vip_only=vip_only,
            freeleech=freeleech,
            fl_vip=fl_vip,
            personal_freeleech=personal_freeleech,
            my_snatched=my_snatched,
            category_id=category_id,
            main_category_id=main_category_id,
            indexer="MyAnonamouse",
            protocol="torrent",
            provider="mam",
            torrent_id=torrent_id,
            requires_dewey_download=True,
            download_url=download_url,
            info_url=info_url,
            description=self._text(item.get("description") or item.get("desc")),
            raw=item,
        )

    def _download_url(self, item: dict[str, Any]) -> str | None:
        direct = self._url(item.get("download") or item.get("download_url") or item.get("downloadUrl"))
        if direct:
            return direct
        token = self._text(item.get("dl"))
        if token:
            return urljoin(self.base_url, f"tor/download.php/{token}")
        return None

    @classmethod
    def _parse_account_status(cls, data: dict[str, Any]) -> MamAccountStatus:
        class_name = cls._first_text(
            data,
            {"class", "classname", "class_name", "user_class", "userclass", "rank", "role"},
        )
        vip_until = cls._first_text(
            data,
            {
                "vip_until",
                "vipuntil",
                "vip_expiry",
                "vip_expires",
                "vip_expires_at",
                "vip_end",
                "vip_end_date",
            },
        )
        explicit_vip = cls._first_text(data, {"is_vip", "vip", "vip_status", "vipstatus"})
        bonus_points = cls._first_int(
            data,
            {"bonus", "bonus_points", "bonuspoints", "seedbonus", "seed_bonus", "points"},
        )
        freeleech_wedges = cls._first_int(
            data,
            {"freeleech_wedges", "freeleechwedges", "fl_wedges", "flwedges", "wedges", "cheese"},
        )
        return MamAccountStatus(
            vip_status=cls._account_vip_status(class_name, vip_until, explicit_vip),
            class_name=class_name,
            vip_until=vip_until,
            bonus_points=bonus_points,
            freeleech_wedges=freeleech_wedges,
        )

    @classmethod
    def _account_vip_status(
        cls,
        class_name: str | None,
        vip_until: str | None,
        explicit_vip: str | None,
    ) -> str:
        explicit = (explicit_vip or "").strip().lower()
        if explicit in {"1", "true", "yes", "active", "vip"}:
            return "active"
        if explicit in {"0", "false", "no", "inactive", "expired"}:
            return "inactive"

        if class_name and "vip" in class_name.lower():
            return "active"
        if vip_until and cls._looks_active_until(vip_until):
            return "active"
        if class_name:
            return "inactive"
        if vip_until:
            return "inactive"
        return "unknown"

    @staticmethod
    def _looks_active_until(value: str) -> bool:
        text = value.strip()
        if not text or text.lower() in {"0", "false", "none", "null", "expired", "never"}:
            return False
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                expires = datetime.strptime(text[:19], pattern).replace(tzinfo=timezone.utc)
                return expires > datetime.now(timezone.utc)
            except ValueError:
                continue
        return True

    @classmethod
    def _first_text(cls, data: Any, keys: set[str]) -> str | None:
        for key, value in cls._walk_items(data):
            if cls._key_name(key) in keys:
                text = cls._text(value)
                if text:
                    return text
        return None

    @classmethod
    def _first_int(cls, data: Any, keys: set[str]) -> int | None:
        for key, value in cls._walk_items(data):
            if cls._key_name(key) in keys:
                parsed = cls._int(value)
                if parsed is not None:
                    return parsed
        return None

    @classmethod
    def _walk_items(cls, value: Any) -> list[tuple[str, Any]]:
        value = cls._decode(value)
        if isinstance(value, dict):
            items: list[tuple[str, Any]] = []
            for key, child in value.items():
                items.append((str(key), child))
                items.extend(cls._walk_items(child))
            return items
        if isinstance(value, list):
            items = []
            for child in value:
                items.extend(cls._walk_items(child))
            return items
        return []

    @staticmethod
    def _key_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    @classmethod
    def _text(cls, value: Any) -> str | None:
        if value is None:
            return None
        value = cls._decode(value)
        if isinstance(value, list):
            parts = [cls._text(item) for item in value]
            return ", ".join(part for part in parts if part) or None
        if isinstance(value, dict):
            for key in ("name", "title", "value", "text"):
                if key in value:
                    return cls._text(value[key])
            return ", ".join(str(part) for part in value.values() if part) or None
        text = unescape(re.sub(r"<[^>]+>", " ", str(value)))
        text = re.sub(r"\s+", " ", text).strip()
        return text or None

    @classmethod
    def _decode(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text in {"{}", "[]", "null", "None"}:
            return None
        if text.startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value

    @classmethod
    def _names(cls, value: Any, *, include_position: bool = False) -> str | None:
        names = cls._name_list(value, include_position=include_position)
        return ", ".join(names) if names else None

    @classmethod
    def _name_list(cls, value: Any, *, include_position: bool = False) -> list[str]:
        value = cls._decode(value)
        if value is None:
            return []
        if isinstance(value, str):
            text = cls._text(value)
            return [text] if text else []
        if isinstance(value, dict):
            names: list[str] = []
            for item in value.values():
                item = cls._decode(item)
                if isinstance(item, list):
                    name = cls._text(item[0]) if item else None
                    if name and include_position and len(item) > 1 and cls._text(item[1]):
                        name = f"{name} #{cls._text(item[1])}"
                else:
                    name = cls._text(item)
                if name:
                    names.append(name)
            return names
        if isinstance(value, list):
            names = []
            for item in value:
                if isinstance(item, dict):
                    name = cls._text(item.get("name") or item.get("title") or item.get("value"))
                elif isinstance(item, list):
                    name = cls._text(item[0]) if item else None
                    if name and include_position and len(item) > 1 and cls._text(item[1]):
                        name = f"{name} #{cls._text(item[1])}"
                else:
                    name = cls._text(item)
                if name:
                    names.append(name)
            return names
        text = cls._text(value)
        return [text] if text else []

    def _url(self, value: Any) -> str | None:
        text = self._text(value)
        if not text:
            return None
        return urljoin(self.base_url, text)

    @classmethod
    def _flags(cls, item: dict[str, Any]) -> list[str]:
        flags: list[str] = []
        checks = {
            "Freeleech": ("free", "freeleech", "fl", "personal_freeleech"),
            "VIP": ("vip", "vip_only", "vip_until"),
            "FL/VIP": ("fl_vip",),
            "Personal FL": ("personal_freeleech",),
            "Snatched": ("my_snatched",),
            "Stream": ("stream", "streamable"),
        }
        for label, keys in checks.items():
            if any(cls._truthy(item.get(key)) for key in keys):
                flags.append(label)
        return flags

    @staticmethod
    def _search_type(value: str) -> str:
        normalized = (value or "all").strip()
        return normalized if normalized in SEARCH_TYPES else "all"

    @staticmethod
    def _has_flag(flags: list[str], label: str) -> bool:
        return any(flag.lower() == label.lower() for flag in flags)

    @staticmethod
    def _truthy(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "freeleech", "vip"}

    @staticmethod
    def _int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        text = str(value).replace(",", "")
        try:
            return int(float(text))
        except ValueError:
            pass
        match = re.search(r"\d+(?:\.\d+)?", text)
        return int(float(match.group(0))) if match else None

    @classmethod
    def _size(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).replace(",", "").strip()
        try:
            return int(float(text))
        except ValueError:
            pass
        match = re.match(r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>[kmgtp]?i?b|bytes?)?", text, flags=re.I)
        if not match:
            return None
        size = float(match.group("size"))
        unit = (match.group("unit") or "b").lower()
        multipliers = {
            "b": 1,
            "byte": 1,
            "bytes": 1,
            "kb": 1000,
            "mb": 1000**2,
            "gb": 1000**3,
            "tb": 1000**4,
            "kib": 1024,
            "mib": 1024**2,
            "gib": 1024**3,
            "tib": 1024**4,
        }
        return int(size * multipliers.get(unit, 1))

    @classmethod
    def _significant_query(cls, query: str) -> str:
        terms = cls._terms(query)
        return " ".join(terms) or query

    @staticmethod
    def _terms(value: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", value.lower())
        return [word for word in words if word not in STOPWORDS and len(word) > 1]

    @classmethod
    def _relevance(cls, query: str, result: SearchResult) -> int:
        title = result.title or ""
        terms = cls._terms(query)
        haystack = " ".join(
            part
            for part in (result.title, result.author, result.series, result.narrator)
            if part
        ).lower()
        title_score = max(
            fuzz.WRatio(query.lower(), title.lower()),
            fuzz.token_set_ratio(cls._significant_query(query), title.lower()),
            fuzz.partial_ratio(cls._significant_query(query), title.lower()),
        )
        people_score = fuzz.token_set_ratio(
            cls._significant_query(query),
            " ".join(part for part in (result.author, result.series) if part).lower(),
        )
        score = max(title_score, people_score * 0.82)
        if terms:
            overlap = sum(1 for term in terms if term in haystack)
            if overlap == 0:
                score = min(score, 35)
            elif overlap < len(terms):
                score = min(score, 60)
            else:
                score += 12
        if cls._significant_query(query).lower() in title.lower():
            score += 15
        return int(max(0, min(round(score), 100)))

    @classmethod
    def _format_matches(cls, result: SearchResult, format_filter: str) -> bool:
        wanted = format_filter.strip().lower()
        if not wanted or wanted == "all":
            return True
        values = [
            result.format,
            result.title,
            result.description,
            " ".join(result.tags),
        ]
        return any(re.search(rf"(^|[^a-z0-9]){re.escape(wanted)}([^a-z0-9]|$)", str(value).lower()) for value in values if value)

    @classmethod
    def _language_matches(cls, result: SearchResult, language_filter: str) -> bool:
        wanted = language_filter.strip().lower()
        if not wanted or wanted == "all":
            return True
        actual = (result.language or "").strip().lower()
        if not actual:
            return False
        wanted_terms = LANGUAGE_ALIASES.get(wanted, {wanted})
        actual_terms = set(re.findall(r"[a-z0-9]+", actual))
        return any(term in actual_terms or term in actual for term in wanted_terms)

    @classmethod
    def _sort_key(cls, query: str, result: SearchResult) -> tuple[int, int, int, int, int]:
        query_terms = cls._terms(query)
        title_terms = cls._terms(result.title or "")
        exact_title = int(query_terms == title_terms)
        starts_with_title = int(bool(query_terms) and title_terms[: len(query_terms)] == query_terms)
        return (
            result.relevance or 0,
            exact_title,
            starts_with_title,
            result.seeders or 0,
            result.snatches or 0,
        )
