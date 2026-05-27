from __future__ import annotations

import httpx

from ..settings import DeweySettings


class AudiobookshelfClient:
    def __init__(self, settings: DeweySettings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.audiobookshelf_url
            and self.settings.audiobookshelf_api_key
            and self.settings.audiobookshelf_library_id
        )

    async def scan_library(self) -> None:
        if not self.configured:
            raise RuntimeError("Audiobookshelf URL, API key, and library ID are required.")

        params = {"force": "1" if self.settings.audiobookshelf_force_scan else "0"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.audiobookshelf_url}/api/libraries/{self.settings.audiobookshelf_library_id}/scan",
                params=params,
                headers={"Authorization": f"Bearer {self.settings.audiobookshelf_api_key}"},
            )
            response.raise_for_status()
