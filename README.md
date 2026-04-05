# Agentic Search (CIIR challenge)

Full-stack pipeline: **topic query → web search → evidence (snippets and/or scrape) → hosted LLM extraction → traceable entity table** (JSON + UI).

## Approach

1. **Search**: **[Tavily](https://tavily.com/)** only — set `TAVILY_API_KEY`. Uses `search_depth=advanced`, `include_raw_content`, and `chunks_per_source=3`. If the key is missing and `MOCK_SEARCH` is false, results fall back to **mock** (startup logs a warning).
2. **Evidence**: **Snippet-first** for lower-ranked hits; the first **`ALWAYS_FETCH_TOP_N`** URLs are always scraped. With **`USE_MONGODB=true`**, MongoDB `url_cache` dedupes across requests. With **`USE_MONGODB=false`**, URL text is cached **only inside that `/search` request** (no database).
3. **Extract**: Default is **Hugging Face Inference** via `InferenceClient.chat_completion` (`LLM_BACKEND=huggingface`): set **`HF_TOKEN`**, **`HF_INFERENCE_PROVIDER`** (e.g. `featherless-ai`), and **`LLM_MODEL`** (default **`meta-llama/Meta-Llama-3.1-8B-Instruct`**). Providers expose this as the **conversational** task, not raw `text_generation`. For **OpenAI-compatible** chat instead, set `LLM_BACKEND=openai` plus `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.

## Local prerequisites

- **Python 3.12+**, **Node 18+**
- **MongoDB** only if **`USE_MONGODB=true`**. Default in `.env.example` is **`USE_MONGODB=false`** (no Mongo process).
- **`TAVILY_API_KEY`** + **`HF_TOKEN`** (default stack) or OpenAI-style keys if `LLM_BACKEND=openai`
- Copy [`backend/.env.example`](backend/.env.example) → `backend/.env` and fill keys.

### Local run

**Backend:**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set TAVILY_API_KEY, HF_TOKEN; optional USE_MONGODB=false
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Frontend:**

```bash
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npm install && npm run dev
```

- App: [http://localhost:3000](http://localhost:3000) · API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### API smoke test

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"open source databases"}'
```

## GitHub and hosting without MongoDB

- **GitHub** holds the **source code** only; it does not run MongoDB for you.
- Set **`USE_MONGODB=false`** on the API service. Then:
  - **URL cache** is a fresh in-memory dict per `/search` (still avoids duplicate fetches *within* one query).
  - **Runs** are kept in **process memory** (last ~256 runs), enough for `GET /runs/{id}` until the process restarts. Multi-instance deploys do not share this store.
- For **durable** history or shared cache across instances, use **`USE_MONGODB=true`** and [MongoDB Atlas](https://www.mongodb.com/atlas) (or the bundled Docker `mongo` service).

## Quick host (GitHub + Render + Vercel)

See **[DEPLOY.md](DEPLOY.md)** for a ~10-minute path: push to GitHub, deploy the API from [`render.yaml`](render.yaml), then deploy `frontend/` on Vercel with `NEXT_PUBLIC_API_URL`.

## Docker (full stack)

Mongo + API + Next.js (production build):

```bash
# Root .env or shell: export TAVILY_API_KEY=... HF_TOKEN=... NEXT_PUBLIC_API_URL=http://localhost:8000
docker compose up --build
```

- UI: [http://localhost:3000](http://localhost:3000) · API: [http://localhost:8000](http://localhost:8000)

`NEXT_PUBLIC_API_URL` must be the **browser-reachable** API URL (same host/port as users use). For production behind HTTPS, use your public API origin.

## Deployment checklist

| Layer | What to configure |
|--------|-------------------|
| **MongoDB** | [Atlas](https://www.mongodb.com/atlas) or managed Mongo — set `MONGODB_URI` on the API service |
| **API** | Deploy [`backend/Dockerfile`](backend/Dockerfile) — env: `TAVILY_API_KEY`, `HF_TOKEN`, …; set **`USE_MONGODB=false`** to skip Mongo, or `USE_MONGODB=true` + `MONGODB_URI` (e.g. Atlas) for persistence |
| **Frontend** | [Vercel](https://vercel.com) or Docker [`frontend/Dockerfile`](frontend/Dockerfile) — build-time `NEXT_PUBLIC_API_URL=https://your-api.example.com` |
| **Secrets** | Never commit `.env`; use host secret managers |

**CORS:** Set `CORS_ORIGINS=https://your-frontend.vercel.app` (no trailing slash). Multiple origins: comma-separated.

**LLM:** Production should use a hosted provider (`LLM_API_KEY` required). `LLM_JSON_OBJECT=false` if your model rejects JSON mode.

## API

- `POST /search` — body: `{ "query": string, "max_results"?: number }` (optional cap 1–30; default from `SEARCH_MAX_RESULTS`)
- `GET /runs/{run_id}` — stored run (snippets, scrape meta, timings)
- `GET /health`

## Hugging Face 403 on Inference Providers

If you see *“does not have sufficient permissions to call Inference Providers”*, your **HF token** is missing the right scope. At [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens), create or edit a **fine-grained** token and turn on **Make calls to Inference Providers** (and enable access to gated models like Llama if you use them). Then set `HF_TOKEN` to that token in `backend/.env` and restart the API.

**Alternative:** set `LLM_BACKEND=openai` and use OpenAI (or any OpenAI-compatible URL) with `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` instead of the HF router.

## Known limitations

- Bot-blocking sites may yield thin evidence; snippet-first helps latency but not coverage.
- Invalid LLM JSON triggers one repair pass; very small models may still struggle.
- Mock search is for offline plumbing tests only.

## License

MIT 
