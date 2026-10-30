# WasteWatch AI — Product Requirements Document

**Status:** As-built + forward-looking · **Last updated:** 2026-10-31 (frontend deployed)
**Owner:** Aakashdeep Srivastava · **License:** MIT

> This PRD is the prose source of truth for *what* WasteWatch AI is, *why* each part
> exists, and the *decisions* behind the architecture. The README remains the
> quickstart / hackathon-submission doc; code lives in the repo. Where this document
> describes something not yet built, it is marked **(planned)**.

---

## 1. Problem

Satellites observe the Earth repeatedly, but observation does not become action.
Illegal dumping, landfill expansion, and land disturbance often go unnoticed until
someone reports them or an inspection team stumbles on them. Conventional satellite
change detection makes this worse, not better: it flags *every* difference — clouds,
seasonal vegetation, illumination shifts, misalignment — producing **noise instead of
intelligence**. An image can show that the ground changed without explaining whether
the change is real, what it is, or whether it matters.

## 2. Product vision

WasteWatch AI behaves like an **environmental analyst**, not an image classifier. It
observes, measures, questions its own results, investigates uncertainty, fuses in the
public environmental record, drafts a regulator-ready brief, and **knows when human
judgment is required**. The guiding principle:

> **An environmental intelligence system must be able to explain its evidence before
> asking someone to act.**

A suspicious region is an *investigation candidate*, never an auto-declared violation.

## 3. Users & primary use cases

| User | Need | How WasteWatch serves it |
|---|---|---|
| Municipal / regulatory analyst | Catch illegal dumping & unpermitted landfill growth early | Detects change, assesses legality vs. permitted sites, drafts a brief to act on |
| Environmental compliance team | Prioritise remote inspections instead of blanket field visits | Ranks review cases by severity + proximity to permitted facilities |
| NGO / watchdog | Monitor known hotspots over time | Multi-date monitoring of AOIs **(planned)** |
| Reviewer (human-in-the-loop) | Confirm or dismiss machine findings with full evidence | Review queue with before/after, change map, trace, and brief |

## 4. Core principle: separation of authority

This is the single most important design rule, enforced throughout the code:

> **CV *measures*. The deterministic policy *decides*. Nemotron *explains*. A human *confirms*.**

- The **deterministic rule policy** (`app/agent.py`) is **authoritative and reproducible**.
  It sets every review state from measured OpenCV metrics.
- **NVIDIA Nemotron on Nebius** (`app/nemotron.py`) is **advisory only** — it describes
  the crop and drafts the brief, and can *never* set or override a review state.
- If no AI key is configured, the CV pipeline runs alone and **no mock AI output is ever
  substituted** — the AI simply renders nothing.
- Final confirmation always belongs to an authorised **human reviewer**.

## 5. The core loop (the product)

The end-to-end user journey and the agent's internal inspection loop:

**User journey (frontend, 8 steps):** explore the globe → select a location (search + draw
polygon/rectangle) → choose real Sentinel-2 dates → watch the agent analyse live → view
results (Before / After / Change tabs, severity legend, stat tiles) → explore regions with
a before/after slider → review (confirm / dismiss / needs-more-info + comment) → track in a
dashboard.

**Agent inspection loop (`app/agent.py`, perceive → decide → act):**

| Stage | Tool | Evidence → next action |
|---|---|---|
| Perceive | `cloud_gate` | AOI cloud fraction `> 0.20` and an alternate exists → `select_alternate_date` |
| Perceive | `coregister` | `< 25` inliers or implausible homography → `refine_ecc` (ECC fallback) |
| Perceive | `detect_change` (coarse, 0.5×) | change score in `(0, 0.60)` with blobs → `inspect_roi_native` |
| Decide | policy | `score ≥ 0.60` → `create_review_case` (`PENDING_REVIEW`); `score ≤ 0` or no blobs → `NO_SIGNIFICANT_CHANGE`; otherwise → `NEEDS_REVIEW` (safe default) |
| Interpret | Nemotron + enrichment | *advisory only*, runs for reviewable states (see §7) |
| Act | human | authorised reviewer approves / dismisses the case |

Key innovation: the system changes its own inspection strategy from measured evidence —
coarse downsampled first pass, native-resolution re-inspection of the top uncertain region
(which adds genuinely new pixels, not just upscaling).

## 6. System architecture (current build)

Two services:

- **Backend — FastAPI (`app/`)**: OpenCV 5 vision engine (`vision.py`) + the deterministic
  agent (`agent.py`) + real Sentinel-2 imagery (`satellite.py`) + the Nemotron interpretation
  layer (`nemotron.py`) + the open-data enrichment layer (`enrich.py`) + review-state store
  (`store.py`). **Pydantic** request + response models (`app/models.py`) type the API surface
  (`response_model=` on `/health`, `/scenes`, `/geocode`, `/alerts`, `/approve`, `/inspect`) and
  validate the inspection record at build time. Endpoints: `/health` (live provider), `/geocode`
  (keyless OSM place search), `/scenes` (real Sentinel-2 L2A via Element84 Earth Search / STAC),
  `/inspect/scene/stream` (clip chosen scenes to AOI + stream the agent live over SSE),
  `/inspect/stream` (manual upload), `/alerts` (dashboard list), `/approve/{id}` (token-guarded
  human review), `/limits` (live rate-limit + AI-budget state), `/admin/limits` (token-guarded
  runtime tuning). Cost-aware rate limiting (`app/ratelimit.py`) guards every paid/expensive path.
- **Frontend — Next.js 16 / React 19 / TypeScript / Tailwind (`frontend/`)**: the full 8-step
  journey. **State: Zustand** for client/journey state (`lib/store.ts`), **TanStack Query** for
  request/response server state (`lib/queries.ts`). Proxies `/api/*` to the backend (no CORS; SSE
  streams through). The browser never talks to the backend directly in production.

### 6.1 State management

Client and server state are deliberately separated:

- **Client / journey state → Zustand** (`lib/store.ts`): the 8-step flow (`selection`,
  `locationName`, `liveSteps`, `result`, `running`, `error`) lives in one store. Steps are
  *derived from state* (conditional rendering), not a counter. A transient `flyTo` signal drives
  the imperative MapLibre camera via an effect in `app/page.tsx`.
- **Server / request-response state → TanStack Query** (`lib/queries.ts`): `useGeocode` /
  `useScenes` (mutations, user-triggered), `useAlerts` (cached query for the dashboard),
  `useReview` (mutation; invalidates the alerts cache on success so the dashboard auto-refreshes).
- **The inspection run is SSE, not TanStack Query.** TanStack Query models request/response, not
  streams. `useRunInspection` drives the SSE stream imperatively, writes each `perceive→decide→act`
  step into the Zustand store, and invalidates the alerts cache when the result arrives. This
  boundary is intentional and documented — the stream is first-class, just not a query.

**Real satellite imagery:** Step 3 reads **real Sentinel-2 L2A** from the public AWS
`sentinel-cogs` bucket via Earth Search (STAC), **no API key**. The backend windowed-reads the
true-colour COG and clips to the AOI with rasterio/GDAL (only the needed bytes). If rasterio is
unavailable, the app degrades to manual before/after upload.

## 7. AI & agentic layer

### 7.1 Tiered Nemotron (on Nebius Token Factory, OpenAI-compatible)

| Tier | Model (default, env-overridable) | Job |
|---|---|---|
| Vision | `nvidia/Nemotron-3.5-Super-VL` | Look at the disputed crop, name what it visually is |
| Reasoning | `nvidia/nemotron-3-super-120b-a12b` | Fuse CV metrics + open data → the brief |
| Deep | `nvidia/Nemotron-3-Ultra-550b-a55b` | High-severity cases (`score ≥ 0.60`) escalate to the flagship reasoner |

Served through Nebius Token Factory's OpenAI-compatible API (`NEBIUS_BASE_URL`), keyed by
`NEBIUS_API_KEY`. Absent key → every AI function returns `None` and the pipeline is unchanged.

### 7.2 Global open-data enrichment (`app/enrich.py`)

For any detected change worldwide, ask the open record *"what is officially known here?"* —
the signal Nemotron reasons over for legality and severity:

- **OpenStreetMap Overpass** (keyless) — distance to the nearest permitted waste facility
  (far from any permitted site → leans unpermitted; on top of one → leans permitted expansion).
- **Open-Meteo Air Quality** (keyless) — PM2.5 / PM10 near the site.
- **Tavily** (optional key) — recent local dumping/landfill news & complaints.

Regional deep layers documented as drop-in extensions: 🇺🇸 EPA ECHO / LMOP / Envirofacts ·
🇪🇺 EEA E-PRTR + Copernicus · 🇮🇳 CPCB inventory + Swachhata + data.gov.in.

### 7.3 Observable reasoning

Every inspection emits a structured **trace** (tool, metric, decision, timestamp) streamed live
over SSE and preserved with the case — the foundation for debugging, review, and evaluation.

### 7.4 Cost-aware, dynamic rate limiting (`app/ratelimit.py`)

The backend runs on a small Nebius VM and its expensive path (paid Nemotron inference + Sentinel-2
egress) is the real cost driver, so rate limiting is **by cost and risk**:

- **Cost-tiered per-client token buckets:** `expensive` (inspections, default 20/hr), `moderate`
  (external-API lookups — scenes/geocode, 30/min), `cheap` (local reads, 240/min). Client keyed by
  the real caller IP (first `x-forwarded-for` hop behind the Vercel proxy). Over-limit → `429` with
  `Retry-After`.
- **AI spend ceiling (sustainability lever):** a rolling 24 h cap on paid Nemotron calls
  (`AI_BUDGET_CALLS_PER_DAY`, default 500). When exhausted, inspections **keep running but skip the
  Nemotron brief → CV-only** — the same "no AI → no brief, never mocked" degrade as an unset key. A
  traffic spike or abuse can never run up an unbounded Token Factory bill.
- **"Highly dynamic":** effective limits are recomputed per request as
  `base(tier) × adaptive_factor`, where the factor auto-tightens (×0.5, ×0.25) as the AI budget
  depletes **and** as live inspection concurrency rises, then recovers. Limits/budget are tunable
  **at runtime** via token-guarded `POST /admin/limits` (no redeploy); `GET /limits` exposes the
  full live state (effective limits, 24 h spend vs budget, degrade flag).
- **Config-gated, shipped on:** every knob has an env default (`RL_*`, `AI_BUDGET_*`); set
  `RL_ENABLED=off` to disable.

---

## 8. Decision record — Agentic framework

**Decision:** Adopt **LangGraph** as the agent-orchestration framework, with **LangSmith** for
tracing/evaluation, and **retain the thin NVIDIA NeMo Agent Toolkit wrapper** as an optional
adapter. **Reject Google ADK** for this project. **(planned — documentation decision; no code
migration in this revision.)**

### 8.1 Context

The brief posed "LangGraph vs LangSmith vs Google ADK — which does Nebius have?" Two
clarifications shaped the decision:

1. **Nebius does not ship an agent framework.** Nebius Token Factory (formerly AI Studio) is a
   model backend with an OpenAI-compatible API. The framework is a *client-side* choice pointed
   at Nebius (directly, or via LiteLLM). Nebius publishes an "Agents Blueprint" and a LangChain
   partnership, and ships LangGraph examples — but the orchestration layer is ours to pick.
2. **LangSmith is not an orchestration framework** — it is observability / tracing / eval. It is
   complementary to LangGraph, not an alternative. So the real choice is **LangGraph vs ADK**.

### 8.2 Options considered

| Option | Fit for WasteWatch | Verdict |
|---|---|---|
| **LangGraph** | `app/agent.py` is already a `perceive → decide → act` state machine → maps ~1:1 onto a `StateGraph`; nodes stay plain Python, so the deterministic policy remains authoritative and Nemotron stays advisory exactly as today. First-class Nebius path (LangChain partnership; `ChatOpenAI(base_url=…)` or LiteLLM). | **Chosen** |
| **LangSmith** | Not a framework — tracing/eval. Layers onto LangGraph; replaces/augments our hand-rolled SSE trace for debugging and offline eval (`eval.py`). | **Chosen as complement** |
| **Google ADK** | Reaches Nebius only through a LiteLLM adapter and pulls a Google/Vertex-flavoured dependency into an NVIDIA + Nebius project. Would fight the existing graph shape. | **Rejected** |
| **NeMo Agent Toolkit (NAT)** | Deprecated by NVIDIA (Oct 2026, EOL end-2026). Already wrapped in `app/nat_agent.py`. Ships an `aiqtoolkit-langchain` integration that wraps LangChain/LangGraph. | **Retained as optional wrapper** |

### 8.3 Rationale

- **Lowest-friction migration:** formalises the graph we already built instead of imposing a new
  mental model.
- **Preserves the core principle (§4):** LangGraph nodes are ordinary Python, so the deterministic
  policy keeps full authority; the LLM never becomes the decision-maker.
- **Strong Nebius support:** documented LangGraph-on-Nebius path; no vendor-mismatch.
- **Satisfies the "NVIDIA agentic framework" requirement without deprecation risk:** build in
  LangGraph, keep the optional NAT wrapper (via `aiqtoolkit-langchain`) as the NVIDIA checkbox,
  and be honest that NAT is EOL.

### 8.4 Consequences / follow-ups (planned)

- Port `run_inspection()` to a `StateGraph`: nodes `cloud_gate`, `coregister`/`refine_ecc`,
  `detect_change`, `inspect_roi_native`, `decide`, `interpret`; conditional edges on the existing
  thresholds. **No behaviour change** — the policy and thresholds are unchanged.
- Add LangSmith tracing behind an env flag (ship dormant; activate by config), keeping the live SSE
  trace for the UI.
- Keep `app/nat_agent.py` import-guarded and optional, as now.
- Nebius model access stays via the OpenAI-compatible client already in `nemotron.py`.

---

## 9. Non-functional requirements

- **Reproducibility:** identical inputs → identical verdicts (deterministic policy).
- **Graceful degradation / fallback chains:** no AI key → CV-only; rasterio missing → manual
  upload; every external dependency has a degradation path.
- **Privacy & security:** reviewer-token-guarded approvals today; per-user identity, rate limiting,
  and production auth are planned. Secrets via env / platform secret-refs, never committed.
- **Cost-awareness:** Nemotron tiering — routine briefs on Super, only high-severity on Ultra; plus
  cost-tiered rate limiting and a 24 h AI spend ceiling that degrades to CV-only (see §7.4).
- **Attribution & etiquette:** each external source carries its license and required attribution;
  cache, don't hammer.
- **Accessibility:** status conveyed by colour + icon + label, not colour alone.
- **Typed contract:** Pydantic response models give the API a validated, self-documented OpenAPI
  schema; CV fields are strictly typed while LLM/open-data payloads stay free-form `dict` (so a
  reshaped upstream response degrades to a logged warning + raw dict, never a 500 mid-stream).

## 10. Honest limitations ledger (current build)

- **Per-inspection images are not archived.** Clips overwrite fixed files
  (`out/in_before.png`, `in_after.png`, `change_map.png`); the dashboard shows an inspection's
  metadata/regions but not its original imagery on revisit. Per-id artifact storage is a TODO.
- **Cloud gate is an RGB heuristic**, not the Sentinel-2 Scene Classification (SCL) mask (the
  true-colour COG is an 8-bit visualisation, not raw reflectance).
- **`disturbed_surface` is a heuristic**, not a verified waste classification — candidates for
  human review, never confirmed violations.
- **Auth is a shared dev reviewer token** — no per-user identity / rate limiting / production auth
  yet. Set `REVIEWER_TOKEN` in production.
- **Deployment — partial.** Frontend is **live on Vercel**: https://wastewatch-ai-psi.vercel.app
  (public, UI/globe loads). The **backend is not yet hosted**: target is a Nebius AI Cloud VM, but
  `compute.instance.create` is PermissionDenied because the tenant's compute is not enabled
  (project quota granted; tenant pool root-controlled). Until the backend is online and
  `FASTAPI_ORIGIN` points at it, the deployed UI loads but data/AI features (search, scenes,
  inspect) return errors. Token Factory key is validated and ready; code is on `main`; the VM
  create is staged — so once compute is enabled this is a ~5-minute finish.
- **Agentic framework is documented, not yet migrated** — the LangGraph/LangSmith decision above is
  a planned refactor; the shipping agent is still the hand-rolled state machine.
- **Rate-limit + AI-budget state is per-process** (exact on one VM). With multiple replicas each gets
  its own share; a shared Redis store (`storage_uri`) would make it global. Documented in
  `app/ratelimit.py`, not hidden.

## 11. Roadmap

1. **Framework migration (planned):** `agent.py` → LangGraph `StateGraph`; LangSmith tracing behind
   a flag; retain optional NAT wrapper.
2. Complete the full web review workflow; per-id artifact persistence.
3. Harden auth & persistence (per-user identity, rate limiting).
4. Cloud deployment on Nebius AI Cloud; reproducible evaluation results.
5. Satellite-specific cloud masking (SCL), geospatial metadata, multi-date monitoring, rigorous
   change-detection benchmarks.
6. Longer term: periodic landfill/dumping monitoring, municipal alerts, inspection prioritisation,
   land-disturbance monitoring, field-verification integration.

---

*WasteWatch AI — from observing the Earth to acting on what matters.*
