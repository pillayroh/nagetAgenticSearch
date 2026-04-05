import asyncio

import httpx
import trafilatura

from app.config import Settings
from app.url_cache_store import UrlCacheStore


async def fetch_text(url: str, settings: Settings) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AgenticSearchBot/1.0; +https://example.local)",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        timeout=settings.scrape_timeout_s,
        follow_redirects=True,
        headers=headers,
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        html = r.text
    extracted = trafilatura.extract(html, url=url, include_comments=False, include_tables=True)
    if extracted and len(extracted.strip()) > 80:
        return extracted.strip()
    return trafilatura.extract(html, include_comments=False, include_tables=True) or html[:8000]


async def scrape_urls(
    urls: list[str],
    cache: UrlCacheStore,
    settings: Settings,
) -> list[dict]:
    rows = [{"url": u, "snippet": ""} for u in urls]
    return await scrape_from_search_results(rows, cache, settings)


async def scrape_from_search_results(
    search_results: list[dict],
    cache: UrlCacheStore,
    settings: Settings,
) -> list[dict]:
    """
    For each hit, use search snippet as page text when long enough (faster than HTTP fetch).
    Otherwise fetch and extract with trafilatura.
    """
    sem = asyncio.Semaphore(settings.max_concurrent_fetches)
    min_snip = settings.snippet_first_min_chars
    top_n = max(0, int(settings.always_fetch_top_n))

    rows = [r for r in search_results if (r.get("url") or "").strip()]

    async def one(idx: int, row: dict) -> dict:
        u = (row.get("url") or "").strip()
        snip = (row.get("snippet") or "").strip()
        force_fetch = idx < top_n
        async with sem:
            try:
                if not u:
                    return {"url": u, "text": "", "error": "empty url"}
                cached = await cache.get_cached_text(u)
                if cached:
                    return {
                        "url": u,
                        "text": cached,
                        "from_cache": True,
                        "source": "cache",
                    }
                if (
                    not force_fetch
                    and settings.snippet_first
                    and len(snip) >= min_snip
                ):
                    await cache.save_cache(u, snip)
                    return {
                        "url": u,
                        "text": snip,
                        "from_cache": False,
                        "source": "search_snippet",
                    }
                text = await fetch_text(u, settings)
                await cache.save_cache(u, text)
                return {
                    "url": u,
                    "text": text,
                    "from_cache": False,
                    "source": "fetched",
                }
            except Exception as e:
                return {
                    "url": u,
                    "text": snip if snip else "",
                    "error": str(e),
                    "source": "error",
                }

    return await asyncio.gather(*[one(i, r) for i, r in enumerate(rows)])


def chunk_text(text: str, max_chars: int, max_chunks: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < max_chunks:
        end = min(start + max_chars, len(text))
        chunk = text[start:end]
        chunks.append(chunk)
        start = end
    return chunks
