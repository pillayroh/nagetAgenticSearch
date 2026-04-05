import logging
import time
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import ensure_indexes, get_database
from app.memory_runs import get_run as memory_get_run
from app.memory_runs import save_run as memory_save_run
from app.pipeline.extract import extract_entities
from app.pipeline.scrape import scrape_from_search_results
from app.pipeline.search import web_search
from app.schemas import SearchRequest, SearchResponse
from app.url_cache_store import MemoryUrlCacheStore, MongoUrlCacheStore

logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Search", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    await ensure_indexes()
    s = get_settings()
    backend = (s.llm_backend or "huggingface").strip().lower()
    if backend == "huggingface" and not s.hf_token.strip():
        logger.warning(
            "HF_TOKEN is empty — POST /search will fail until you set Hugging Face inference credentials."
        )
    elif backend == "openai" and not s.llm_api_key.strip():
        logger.warning(
            "LLM_API_KEY is empty — POST /search will fail until you set OpenAI-compatible credentials."
        )
    if not s.mock_search and not s.tavily_api_key.strip():
        logger.warning(
            "TAVILY_API_KEY is empty — search will use mock results until you set Tavily credentials."
        )
    if not s.use_mongodb:
        logger.info(
            "USE_MONGODB=false — URL cache is per-request only; runs stored in process memory (lost on restart)."
        )


def _cors_origins() -> list[str]:
    return [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "use_mongodb": get_settings().use_mongodb}


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    settings = get_settings()
    max_results = req.max_results
    if max_results is None:
        max_results = settings.search_max_results

    t0 = time.perf_counter()
    try:
        raw_results, search_provider = await web_search(
            req.query.strip(), max_results, settings
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Search failed: {e}") from e

    seen: set[str] = set()
    results: list[dict] = []
    for r in raw_results:
        u = (r.get("url") or "").strip()
        if u and u not in seen:
            seen.add(u)
            results.append(r)
    urls = list(dict.fromkeys(r["url"] for r in results if r.get("url")))

    if settings.use_mongodb:
        db = get_database()
        url_cache: MemoryUrlCacheStore | MongoUrlCacheStore = MongoUrlCacheStore(
            db.url_cache
        )
    else:
        db = None
        url_cache = MemoryUrlCacheStore({})

    scraped = await scrape_from_search_results(results, url_cache, settings)

    t1 = time.perf_counter()
    try:
        llm_out = await extract_entities(
            req.query.strip(),
            results,
            scraped,
            settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM extraction failed: {e}") from e
    t2 = time.perf_counter()

    column_order = llm_out.get("column_order") or []
    entities = llm_out.get("entities") or []
    if not isinstance(column_order, list):
        column_order = []
    if not isinstance(entities, list):
        entities = []

    timings = {
        "search_scrape": round(t1 - t0, 3),
        "llm": round(t2 - t1, 3),
        "total": round(t2 - t0, 3),
    }
    scrape_meta = [
        {
            "url": x["url"],
            "error": x.get("error"),
            "from_cache": x.get("from_cache"),
            "source": x.get("source"),
        }
        for x in scraped
    ]

    if settings.use_mongodb:
        assert db is not None
        oid = ObjectId()
        run_id = str(oid)
        doc = {
            "_id": oid,
            "query": req.query.strip(),
            "created_at": datetime.now(timezone.utc),
            "column_order": column_order,
            "entities": entities,
            "search_urls": urls,
            "search_snippets": results,
            "scrape_meta": scrape_meta,
            "search_provider": search_provider,
            "timings_s": timings,
        }
        await db.runs.insert_one(doc)
    else:
        run_id = str(uuid.uuid4())
        doc = {
            "_id": run_id,
            "query": req.query.strip(),
            "created_at": datetime.now(timezone.utc),
            "column_order": column_order,
            "entities": entities,
            "search_urls": urls,
            "search_snippets": results,
            "scrape_meta": scrape_meta,
            "search_provider": search_provider,
            "timings_s": timings,
        }
        memory_save_run(run_id, doc)

    meta = {
        "timings_s": timings,
        "search_provider": search_provider,
        "pages_fetched": len([x for x in scraped if not x.get("error")]),
        "pages_from_snippet": sum(
            1 for x in scraped if x.get("source") == "search_snippet"
        ),
        "pages_fetched_http": sum(
            1 for x in scraped if x.get("source") == "fetched"
        ),
        "persistence": "mongodb" if settings.use_mongodb else "memory",
    }

    return SearchResponse(
        run_id=run_id,
        query=req.query.strip(),
        column_order=column_order,
        entities=entities,
        search_urls=urls,
        meta=meta,
    )


def _serialize_run(doc: dict) -> dict:
    out = dict(doc)
    _id = out.get("_id")
    if _id is not None:
        out["_id"] = str(_id)
    ca = out.get("created_at")
    if ca is not None and hasattr(ca, "isoformat"):
        out["created_at"] = ca.isoformat()
    return out


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    settings = get_settings()
    if settings.use_mongodb:
        try:
            oid = ObjectId(run_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid run id") from e
        db = get_database()
        doc = await db.runs.find_one({"_id": oid})
        if not doc:
            raise HTTPException(status_code=404, detail="Run not found")
        return _serialize_run(doc)

    doc = memory_get_run(run_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(doc)
