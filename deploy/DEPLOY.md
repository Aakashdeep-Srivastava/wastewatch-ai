# Deploying WasteWatch AI

Two services: **backend on Nebius AI Cloud**, **frontend on Vercel**. The browser
only ever talks HTTPS to Vercel; Vercel proxies `/api/*` to the backend server-side
(see `frontend/next.config.ts`), so there is **no CORS** and the backend can serve
plain HTTP. SSE (the live agent stream) passes through the proxy unchanged.

```
Browser ──https──► Vercel (Next.js)  ──http──►  Nebius VM :8000 (FastAPI)
                   rewrites /api/* ─────────────► NVIDIA Nemotron @ Nebius Token Factory
```

## 1. Backend — Nebius AI Cloud (do this first; you need its URL for the frontend)

CPU-only (Nemotron runs remotely on Token Factory), so a small VM is enough.

1. **Nebius console → Compute → Create VM**: Ubuntu 24.04, 2 vCPU / 4 GB, **public IP on**.
2. **Firewall / security group**: allow inbound **TCP 8000** and **22**.
3. **SSH in** and run (paste your real key + the exact base URL/model IDs from
   tokenfactory.nebius.com):
   ```bash
   export NEBIUS_API_KEY=sk-...
   export NEBIUS_BASE_URL=https://api.studio.nebius.com/v1/   # or your dashboard's URL
   export TAVILY_API_KEY=...                                  # optional
   curl -fsSL https://raw.githubusercontent.com/Aakashdeep-Srivastava/wastewatch-ai/main/deploy/nebius_vm_setup.sh | bash
   ```
4. Confirm: `curl http://<VM_PUBLIC_IP>:8000/health` → `"ai": { "available": true }`.

Backend URL = `http://<VM_PUBLIC_IP>:8000`.

## 2. Frontend — Vercel

From `frontend/`:
```bash
cd frontend
vercel link          # pick/create the project
vercel env add FASTAPI_ORIGIN production   # paste http://<VM_PUBLIC_IP>:8000
vercel deploy --prod
```
The deployed Vercel URL is your **public demo URL** for the Devpost submission.

## Notes
- No key? The backend still runs the deterministic CV pipeline; the Nemotron brief is
  simply absent (never mocked). Add `NEBIUS_API_KEY` and `docker restart wastewatch`.
- Container logs: `sudo docker logs -f wastewatch`.
- The local JSON alert store is per-container; set `ORBIT_STORE=dynamo` only if you
  wire a persistent store (not needed for the demo).
