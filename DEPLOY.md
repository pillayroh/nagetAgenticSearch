# Fast deploy (~10 minutes)

## 1) Push code to GitHub

Create a repo, then from your machine:

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOU/YOUR-REPO.git
git branch -M main
git push -u origin main
```

## 2) API on Render (free)

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint**.
2. Connect the GitHub repo → Render reads [`render.yaml`](render.yaml).
3. After the blueprint is created, open the **agentic-search-api** service → **Environment**:
   - Set **`TAVILY_API_KEY`**, **`HF_TOKEN`**.
   - Set **`CORS_ORIGINS`** to `http://localhost:3000` for now (after Vercel is live, add your production URL per §4 and redeploy).
4. Wait for deploy → copy the service URL, e.g. `https://agentic-search-api.onrender.com`.

Cold starts on the free tier can take ~30–60s on first request.

## 3) Frontend on Vercel (free)

1. [vercel.com/new](https://vercel.com/new) → import the same GitHub repo.
2. **Root Directory**: `frontend`.
3. **Environment Variables**:
   - `NEXT_PUBLIC_API_URL` = your Render API URL **with no trailing slash**, e.g. `https://agentic-search-api.onrender.com`
4. Deploy.

## 4) CORS (required once)

On Render → API service → **Environment** → set **`CORS_ORIGINS`** to:

`https://YOUR-APP.vercel.app,http://localhost:3000`

(scheme + host only, no trailing slash, comma-separated). **Save** and **Manual Deploy** so the API picks it up.

## Check

- API: `https://YOUR-API.onrender.com/health` → `{"ok":true,"use_mongodb":false}`
- App: open your Vercel URL and run a search.
