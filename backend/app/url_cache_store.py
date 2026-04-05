"""URL text cache: MongoDB collection or in-memory (per-request) dict."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from motor.motor_asyncio import AsyncIOMotorCollection


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


@runtime_checkable
class UrlCacheStore(Protocol):
    async def get_cached_text(self, url: str) -> str | None: ...

    async def save_cache(self, url: str, text: str) -> None: ...


class MemoryUrlCacheStore:
    """Per-request cache: dedupes fetches only within a single /search call."""

    def __init__(self, backing: dict[str, str] | None = None) -> None:
        self._data = backing if backing is not None else {}

    async def get_cached_text(self, url: str) -> str | None:
        return self._data.get(url_hash(url))

    async def save_cache(self, url: str, text: str) -> None:
        self._data[url_hash(url)] = text


class MongoUrlCacheStore:
    def __init__(self, coll: AsyncIOMotorCollection) -> None:
        self._coll = coll

    async def get_cached_text(self, url: str) -> str | None:
        doc = await self._coll.find_one({"url_hash": url_hash(url)})
        if doc and doc.get("text"):
            return doc["text"]
        return None

    async def save_cache(self, url: str, text: str) -> None:
        now = datetime.now(timezone.utc)
        h = url_hash(url)
        await self._coll.update_one(
            {"url_hash": h},
            {
                "$set": {"url": url, "text": text, "fetched_at": now},
                "$setOnInsert": {"url_hash": h},
            },
            upsert=True,
        )
