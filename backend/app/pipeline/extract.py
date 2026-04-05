import asyncio
import json
import re
from typing import Any

from huggingface_hub import InferenceClient
from openai import AsyncOpenAI

from app.config import Settings


def _build_evidence(
    pages: list[dict],
    chunk_chars: int,
    max_chunks_per_url: int,
    snippets: dict[str, str],
) -> str:
    from app.pipeline.scrape import chunk_text

    blocks = []
    for p in pages:
        url = p.get("url") or ""
        text = (p.get("text") or "").strip()
        if not text and url:
            text = (snippets.get(url) or "").strip()
        if not text:
            continue
        parts = chunk_text(text, chunk_chars, max_chunks_per_url)
        for i, part in enumerate(parts):
            blocks.append(f"### SOURCE\nurl: {url}\nchunk_index: {i}\n---\n{part}\n")
    return "\n".join(blocks) if blocks else "(no page text retrieved; use snippets only)"


def _snippets_map(search_results: list[dict]) -> dict[str, str]:
    return {r["url"]: r.get("snippet") or "" for r in search_results if r.get("url")}


SYSTEM = """You extract structured entities for a research table from web evidence only.
Rules:
- Every cell must be shaped EXACTLY as: { "value": string|null, "confidence": number 0-1, "sources": [ { "url": string, "evidence": string } ] } under cells.<column_name>. Do not put company names or confidence at the same level as column keys.
- sources[].url must be ONLY the exact URL from the line \"url: ...\" in that SOURCE block — never append \"chunk\", \"chunk_index\", or spaces after the URL.
- evidence must be a short verbatim quote from the same SOURCE body.
- Output a single JSON object with keys: column_order (array of strings), entities (array).
- Respect the max entity count given in the user message; prefer quality over quantity.
- column_order lists data columns only (e.g. name, description, focus_area) — never the word \"cells\".
- Do not invent URLs.
- If evidence is thin, return fewer entities rather than padding.
- Respond with one raw JSON object only. No markdown code fences, no text before or after the JSON."""


def _hf_chat_completion(settings: Settings, messages: list[dict[str, str]]) -> str:
    """HF Inference `chat_completion` (conversational) — required by providers e.g. featherless-ai."""
    client = InferenceClient(
        provider=settings.hf_inference_provider,
        api_key=settings.hf_token,
    )
    try:
        out = client.chat_completion(
            messages=messages,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=0.2,
        )
    except Exception as e:
        low = str(e).lower()
        if (
            "403" in str(e)
            or "inference providers" in low
            or "sufficient permissions" in low
        ):
            raise ValueError(
                "Hugging Face token cannot call Inference Providers. At "
                "https://huggingface.co/settings/tokens create or edit a fine-grained token and enable "
                "'Make calls to Inference Providers', then set HF_TOKEN and restart. "
                "Alternatively set LLM_BACKEND=openai with LLM_API_KEY / LLM_BASE_URL / LLM_MODEL."
            ) from e
        raise
    if not out.choices:
        return ""
    content = out.choices[0].message.content
    return (content or "").strip()


def _normalize_table(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"column_order": [], "entities": []}
    cols = data.get("column_order")
    if cols is None:
        cols = data.get("columns")
    if not isinstance(cols, list):
        cols = []
    ents = data.get("entities")
    if ents is None:
        ents = data.get("results") or data.get("rows")
    if not isinstance(ents, list):
        ents = []
    return {"column_order": cols, "entities": ents}


def _is_empty_table(data: dict[str, Any]) -> bool:
    d = _normalize_table(data)
    return len(d.get("entities") or []) == 0


def _fix_column_order(data: dict[str, Any]) -> dict[str, Any]:
    """If column_order is missing or does not match row keys, derive from the first entity."""
    ents = data.get("entities") or []
    co = data.get("column_order") or []
    if not ents or not isinstance(ents[0], dict):
        return data
    cells0 = ents[0].get("cells")
    if not isinstance(cells0, dict) or not cells0:
        return data
    keys = list(cells0.keys())
    valid = (
        bool(co)
        and "cells" not in co
        and all(isinstance(c, str) and c in cells0 for c in co)
    )
    if not valid:
        data = dict(data)
        data["column_order"] = keys
    return data


def _clean_source_url(url: str) -> str:
    if not isinstance(url, str):
        return url
    u = url.strip()
    if " chunk=" in u:
        u = u.split(" chunk=")[0].strip()
    u = re.sub(r"\s+chunk=\d+\s*$", "", u, flags=re.IGNORECASE).strip()
    return u


def _slug_col(name: str) -> str:
    return str(name).lower().replace(" ", "_").replace("-", "_")


def _normalize_cell_obj(v: Any) -> dict[str, Any]:
    """Ensure UI/API contract: each cell is { value, confidence?, sources? }."""
    if v is None:
        return {"value": None, "confidence": None, "sources": []}
    if isinstance(v, (str, int, float, bool)):
        return {"value": str(v), "confidence": None, "sources": []}
    if isinstance(v, dict):
        out = {**v}
        val = out.get("value")
        if isinstance(val, dict):
            for k in ("text", "content", "label", "name", "value"):
                if isinstance(val.get(k), str) and val[k].strip():
                    out["value"] = val[k]
                    break
            else:
                out["value"] = None
        if "value" not in out:
            out["value"] = None
        empty_val = out.get("value") is None or (
            isinstance(out.get("value"), str) and not str(out["value"]).strip()
        )
        if empty_val:
            for alt in (
                "text",
                "content",
                "label",
                "name",
                "title",
                "description",
                "summary",
                "details",
                "focus_area",
                "focus",
            ):
                if alt in out and isinstance(out[alt], (str, int, float)):
                    s = str(out[alt]).strip()
                    if s:
                        out["value"] = str(out[alt])
                        empty_val = False
                        break
        if empty_val:
            skip = frozenset({"sources", "confidence", "url", "evidence"})
            for k, val in out.items():
                if k in skip:
                    continue
                if isinstance(val, str) and val.strip():
                    out["value"] = val
                    break
                if isinstance(val, (int, float)) and k != "confidence":
                    out["value"] = str(val)
                    break
        if "sources" not in out or not isinstance(out["sources"], list):
            out["sources"] = []
        if "confidence" not in out:
            out["confidence"] = None
        return out
    return {"value": str(v), "confidence": None, "sources": []}


def _ensure_entities_have_cells(data: dict[str, Any]) -> dict[str, Any]:
    """LLMs often return each row as a flat object; wrap into { cells: { ... } }."""
    ents = data.get("entities")
    if not isinstance(ents, list):
        return data
    meta = frozenset({"cells", "entity_id", "id", "_id", "row_index"})
    new_ents: list[Any] = []
    for ent in ents:
        if not isinstance(ent, dict):
            new_ents.append({"cells": {}})
            continue
        if isinstance(ent.get("cells"), dict):
            new_ents.append(ent)
            continue
        cells = {k: v for k, v in ent.items() if k not in meta}
        new_ents.append({"cells": cells})
    out = dict(data)
    out["entities"] = new_ents
    return out


def _normalize_cell_dicts(data: dict[str, Any]) -> dict[str, Any]:
    ents = data.get("entities")
    if not isinstance(ents, list):
        return data
    new_ents: list[Any] = []
    for ent in ents:
        if not isinstance(ent, dict):
            new_ents.append(ent)
            continue
        cells = ent.get("cells")
        if not isinstance(cells, dict):
            new_ents.append(ent)
            continue
        new_cells = {k: _normalize_cell_obj(v) for k, v in cells.items()}
        new_ents.append({**ent, "cells": new_cells})
    out = dict(data)
    out["entities"] = new_ents
    return out


def _align_column_order_to_cells(data: dict[str, Any]) -> dict[str, Any]:
    """Map column_order labels to actual cell keys (e.g. focus_area vs Focus Area)."""
    co = data.get("column_order") or []
    ents = data.get("entities") or []
    if not co or not ents or not isinstance(ents[0], dict):
        return data
    cells0 = ents[0].get("cells")
    if not isinstance(cells0, dict) or not cells0:
        return data
    slug_to_actual = {_slug_col(k): k for k in cells0}
    new_co: list[str] = []
    changed = False
    for c in co:
        if not isinstance(c, str):
            new_co.append(c)
            continue
        if c in cells0:
            new_co.append(c)
            continue
        slug = _slug_col(c)
        if slug in slug_to_actual:
            new_co.append(slug_to_actual[slug])
            changed = True
        else:
            new_co.append(c)
    if changed or any(isinstance(c, str) and c not in cells0 for c in new_co):
        out = dict(data)
        out["column_order"] = new_co
        return out
    return data


def _cap_entity_rows(data: dict[str, Any], max_entities: int) -> dict[str, Any]:
    ents = data.get("entities") or []
    if isinstance(ents, list) and len(ents) > max_entities:
        data = dict(data)
        data["entities"] = ents[:max_entities]
    return data


def _sanitize_urls_in_output(obj: Any) -> None:
    if isinstance(obj, dict):
        if "url" in obj and isinstance(obj["url"], str):
            obj["url"] = _clean_source_url(obj["url"])
        for v in obj.values():
            _sanitize_urls_in_output(v)
    elif isinstance(obj, list):
        for item in obj:
            _sanitize_urls_in_output(item)


async def extract_entities(
    query: str,
    search_results: list[dict],
    scraped_pages: list[dict],
    settings: Settings,
) -> dict[str, Any]:
    chunk_chars = settings.search_chunk_chars
    max_chunks = settings.search_max_chunks_per_url
    max_entities = settings.llm_max_entities

    snippets = _snippets_map(search_results)
    evidence = _build_evidence(scraped_pages, chunk_chars, max_chunks, snippets)
    cap = settings.llm_max_evidence_chars
    if len(evidence) > cap:
        evidence = (
            evidence[:cap]
            + "\n\n[EVIDENCE TRUNCATED — configure LLM_MAX_EVIDENCE_CHARS to raise this cap]\n"
        )

    user = (
        f"User topic query: {query}\n"
        f"Max entities (hard cap): {max_entities}\n\n"
        f"EVIDENCE:\n{evidence}"
    )

    backend = (settings.llm_backend or "huggingface").strip().lower()
    if backend == "huggingface":
        if not settings.hf_token.strip():
            raise ValueError(
                "HF_TOKEN is not set. Hugging Face Inference (e.g. featherless-ai) requires HF_TOKEN in .env."
            )
    else:
        if not settings.llm_api_key.strip():
            raise ValueError(
                "LLM_API_KEY is not set. Set LLM_BACKEND=openai and configure OpenAI-compatible credentials."
            )

    oa_client: AsyncOpenAI | None = None
    oa_model = settings.llm_model
    if backend == "openai":
        oa_client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )

    async def call(messages: list[dict]) -> str:
        if backend == "huggingface":
            hf_messages: list[dict[str, str]] = []
            for m in messages:
                role = m.get("role")
                content = m.get("content")
                if role not in ("system", "user", "assistant") or not isinstance(content, str):
                    continue
                hf_messages.append({"role": role, "content": content})
            return await asyncio.to_thread(_hf_chat_completion, settings, hf_messages)

        assert oa_client is not None
        kwargs = dict(
            model=oa_model,
            messages=messages,
            temperature=0.2,
            max_tokens=settings.llm_max_tokens,
        )
        if settings.llm_json_object:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await oa_client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()

    async def run_extraction(user_content: str) -> dict[str, Any] | None:
        raw_local = await call(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_content},
            ]
        )
        parsed = _safe_parse(raw_local)
        if parsed is None:
            repair = await call(
                [
                    {
                        "role": "system",
                        "content": "Return only valid JSON. Fix the following to match the schema described earlier.",
                    },
                    {"role": "user", "content": raw_local[:12000]},
                ]
            )
            parsed = _safe_parse(repair)
        return parsed

    data = await run_extraction(user)
    if data is None:
        data = {
            "column_order": ["error"],
            "entities": [
                {
                    "cells": {
                        "error": {
                            "value": "LLM returned invalid JSON",
                            "confidence": 0.0,
                            "sources": [],
                        }
                    }
                }
            ],
        }
    else:
        data = _normalize_table(data)
        if _is_empty_table(data):
            short_evidence = evidence[:14000] if len(evidence) > 14000 else evidence
            retry_user = (
                f"User topic query: {query}\n"
                f"Max entities: {max_entities}\n\n"
                "The evidence below may be truncated. "
                "You MUST output 3–5 entities with the required nested cell schema and real source quotes.\n\n"
                f"EVIDENCE:\n{short_evidence}"
            )
            retry_out = await run_extraction(retry_user)
            if retry_out is not None:
                retry_norm = _normalize_table(retry_out)
                if len(retry_norm.get("entities") or []) > 0:
                    data = retry_norm
    data = _ensure_entities_have_cells(data)
    data = _normalize_cell_dicts(data)
    data = _align_column_order_to_cells(data)
    data = _fix_column_order(data)
    data = _cap_entity_rows(data, max_entities)
    _sanitize_urls_in_output(data)
    return data


def _safe_parse(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}\s*$", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None
