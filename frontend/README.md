# WasteWatch AI — Next.js frontend

Next.js 16 (App Router, React 19, TypeScript, Tailwind 4) + MapLibre GL JS.
It talks to the existing FastAPI backend (OpenCV 5 + agent) — the Python code is
unchanged. The browser calls Next.js same-origin at `/api/*`; Next proxies those
to FastAPI (see `next.config.ts`), so there is no CORS and SSE streaming passes
straight through.

## Run locally (two terminals)

Terminal 1 — FastAPI backend (from the repo root):

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — Next.js frontend:

```powershell
cd frontend
Copy-Item .env.local.example .env.local   # FASTAPI_ORIGIN=http://127.0.0.1:8000
npm install
npm run dev
```

Open http://localhost:3000.

## What it does

- Interactive MapLibre satellite globe (NASA GIBS + EOX Sentinel-2), Fly to Goa.
- Draw an AOI (rectangle) or use the current view.
- Upload a before/after pair and **watch the agent reason live** (SSE stream of
  each perceive → decide → act step), then see the result panel.
- Detected change is projected from image pixels to lng/lat and drawn on the
  globe, coloured by disturbed-surface score.
- Human review (approve / dismiss) through the backend's reviewer-token API.

Basemap tiles are historical composites — navigation/context only, not a source
for temporal change detection. Analysis runs on the uploaded Sentinel-2 pair.

## Configuration

- `FASTAPI_ORIGIN` — backend origin the `/api/*` rewrite proxies to.

## Deploy

Next.js and FastAPI are two services. Options: deploy both on AWS App Runner
(set `FASTAPI_ORIGIN` to the backend service URL), or Next.js on Vercel +
FastAPI on App Runner.
