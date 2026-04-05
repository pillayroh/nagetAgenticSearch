import httpx

from app.config import Settings


def _mock_results(query: str, max_results: int) -> list[dict]:
    return [
        {
            "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
            "title": "Artificial intelligence (Wikipedia)",
            "snippet": f"Mock result for query {query!r}. Set TAVILY_API_KEY for live Tavily search.",
        },
        {
            "url": "https://example.com/mock",
            "title": "Example mock page",
            "snippet": "Placeholder entity: MockCo — a fictional company for offline testing.",
        },
    ][: max_results or 2]


async def tavily_search(query: str, max_results: int, settings: Settings) -> list[dict]:
    n = min(max(1, max_results), 20)
    payload: dict = {
        "api_key": settings.tavily_api_key,
        "query": query.strip(),
        "search_depth": "advanced",
        "max_results": n,
        "include_answer": False,
        "include_raw_content": True,
        "chunks_per_source": 3,
    }
    topic = settings.tavily_topic.strip().lower()
    if topic in ("general", "news", "finance"):
        payload["topic"] = topic

    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post("https://api.tavily.com/search", json=payload)
        if r.status_code >= 400 and "chunks_per_source" in payload:
            payload.pop("chunks_per_source", None)
            r = await client.post("https://api.tavily.com/search", json=payload)
        r.raise_for_status()
        data = r.json()

    out: list[dict] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        title = item.get("title") or ""
        parts: list[str] = []
        raw = (item.get("raw_content") or "").strip()
        content = (item.get("content") or "").strip()
        if raw and len(raw) > len(content):
            parts.append(raw[:12000])
        elif content:
            parts.append(content)
        elif raw:
            parts.append(raw)
        snippet = "\n\n".join(parts) if parts else ""
        out.append({"url": url, "title": title, "snippet": snippet})
    return out


async def web_search(
    query: str, max_results: int, settings: Settings
) -> tuple[list[dict], str]:
    """
    Web search via Tavily only (or mock when MOCK_SEARCH=true / no API key).
    """
    if settings.mock_search:
        return _mock_results(query, max_results), "mock"
    if not settings.tavily_api_key.strip():
        return _mock_results(query, max_results), "mock"
    results = await tavily_search(query, max_results, settings)
    return results, "tavily"
