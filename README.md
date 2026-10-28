# WasteWatch AI — From Satellite Change to Environmental Intelligence

**An autonomous satellite monitoring system that detects environmental changes, investigates uncertain evidence, and turns observations into actionable, human-verified intelligence.**

## Inspiration

Every day, satellites capture images of our planet. They observe forests disappearing, land being disturbed, waste sites expanding, and landscapes changing.

But there is a fundamental problem.

**We have the ability to observe the Earth repeatedly. We still struggle to turn those observations into timely action.**

While working on AI-powered waste management and environmental technology, we realised that monitoring large geographical areas remains difficult, expensive, and reactive.

Illegal dumping, landfill expansion, and other potentially harmful activities can go unnoticed until someone reports them or an inspection team discovers them.

Satellite imagery offers a way to monitor these changes, but conventional change detection presents another challenge.

An image may show a difference without explaining its significance. Clouds, vegetation, seasonal variations, illumination, and imperfect alignment can create misleading results.

A system that flags every difference creates noise instead of intelligence.

That led us to a question:

**What if AI could not only detect a change, but also investigate whether the evidence was reliable before asking someone to act?**

We wanted a system that behaves more like an environmental analyst than a conventional image classifier.

A system that observes, measures, questions its own results, investigates uncertainty, and knows when human judgment is required.

That became **WasteWatch AI**.

## What it does

WasteWatch AI turns multi-temporal satellite imagery into an intelligent environmental monitoring and investigation workflow.

A user provides satellite images of the same location captured at different times. The platform processes the images, identifies meaningful changes, evaluates their visual characteristics, and determines whether additional investigation is necessary.

Rather than producing a single prediction, WasteWatch AI follows a multi-stage process:

- **Observe:** Ingest satellite imagery and assess its quality.
- **Align:** Use OpenCV 5 to register images and evaluate geometric reliability.
- **Detect:** Identify changed regions through image processing and spatial analysis.
- **Investigate:** Automatically execute additional processing when measurements indicate uncertainty.
- **Interpret:** Examine the visual characteristics of potentially disturbed ground.
- **Decide:** Distinguish between low-change, uncertain, and review-worthy observations.
- **Verify:** Present evidence to a human reviewer before confirmation.
- **Record:** Preserve inspection results, visual artifacts, and the agent's decision trace.

The key idea is simple:

**WasteWatch AI does not stop when it detects a change. It determines what should happen next.**

A suspicious region is treated as an environmental investigation candidate, not automatically declared an illegal dumping site.

This makes the platform applicable to waste monitoring today, with potential extensions to land disturbance, encroachment, industrial expansion, and environmental compliance.

## How we built it

We designed WasteWatch AI as a modular computer vision and autonomous decision-making system using Python, OpenCV 5, FastAPI, and an AWS-oriented architecture.

The system separates visual perception, decision-making, and human verification.

### 1. Satellite imagery ingestion

The workflow begins with two satellite images representing the same area at different observation dates.

The backend accepts image uploads, checks whether the files can be decoded, and applies image-size limits.

An optional alternative-date image can also be supplied.

Before comparison, the vision pipeline assesses whether the imagery is suitable for analysis.

The current RGB-based quality check estimates potential cloud coverage using colour and brightness characteristics.

When the cloud estimate exceeds the configured threshold, the inspection controller can switch to the supplied alternative observation.

This prevents the workflow from blindly processing every image pair as equally reliable.

### 2. Robust image registration with OpenCV 5

Comparing images captured at different times requires careful alignment.

A small positioning error can cause unchanged structures, roads, or vegetation boundaries to appear as false changes.

We implemented an OpenCV 5 registration pipeline using:

- ORB feature detection and descriptor matching
- Brute-force descriptor matching
- `findHomography` with explicitly selected `USAC_MAGSAC`
- Geometric plausibility and feature-inlier checks
- `warpPerspective` for image alignment
- Enhanced Correlation Coefficient (ECC) alignment as a fallback

The system evaluates whether the estimated transformation is sufficiently supported by the image evidence.

When registration is weak or geometrically implausible, the agent invokes the ECC-based alternative rather than unconditionally accepting the original result.

**Registration quality directly affects the next action taken by the system.**

### 3. Multi-temporal change detection

After image alignment, WasteWatch AI analyses differences between the earlier and later observations.

We built a classical computer vision pipeline that combines:

- Lab colour-space comparison
- Cross-date colour normalization
- Gaussian smoothing
- Otsu thresholding
- Morphological noise reduction
- Connected-component analysis
- Region-level bounding boxes and spatial measurements

The pipeline identifies candidate changed regions and produces visual artifacts showing where differences occurred.

Each region is evaluated using measurable features, including its approximate pixel area and visual characteristics.

We also developed a disturbed-surface scoring heuristic based on brightness, saturation, greenness, and texture.

Importantly, this measurement represents potential surface disturbance, not a confirmed waste classification.

The system retains the distinction between what computer vision can measure and what requires further interpretation.

### 4. Autonomous visual investigation

This is the central technical innovation.

Traditional image-processing workflows run a predefined sequence and return an output.

WasteWatch AI uses the results of one operation to determine which operation should execute next.

Its inspection controller evaluates the measurements returned by OpenCV and chooses between actions such as:

| Evidence observed | System response |
|---|---|
| Potential cloud obstruction | Select an available alternate observation |
| Weak geometric registration | Retry alignment using ECC |
| Uncertain change score | Reinspect the region at native resolution |
| Significant surface change | Create a human-review case |
| Ambiguous results | Request human evaluation |
| No significant detected change | Record the inspection outcome |

We implemented coarse-to-native-resolution analysis to make the reinvestigation step meaningful.

The initial change-detection pass operates on a downsampled image.

When an uncertain region is found, the controller selects a candidate and processes that area using the original-resolution image data.

This provides additional visual information that was unavailable during the initial reduced-resolution pass.

**The system changes its own inspection strategy based on measured evidence.**

### 5. Structured decision-making and optional multimodal reasoning

We separated decision authority from optional semantic interpretation.

The primary agent uses measurable visual metrics and deterministic rules to decide which processing tools to call and when to escalate a result.

This makes decisions reproducible and easier to inspect.

We also implemented an optional Amazon Bedrock semantic adviser capable of examining ambiguous image regions and suggesting visual categories.

The adviser does not independently confirm environmental violations or override the inspection policy.

The system's authoritative decisions remain governed by the measured evidence and defined review rules.

### 6. Web application and inspection workflow

We developed a FastAPI application with endpoints for running inspections, retrieving their execution traces, and processing reviewer decisions.

The browser interface provides a starting point for the complete user workflow:

**Upload imagery → Run inspection → Examine detected changes → Review agent decisions → Evaluate findings**

The processing results include generated image artifacts and a structured trace describing the operations performed.

Our longer-term interface design extends this into an environmental operations dashboard with inspection history, geographic visualisation, candidate regions, alert queues, and reviewer workflows.

### 7. AWS infrastructure

WasteWatch AI includes an AWS deployment path designed around Amazon EC2, with optional DynamoDB persistence and Amazon Bedrock reasoning.

The core vision pipeline can operate locally without requiring a cloud-hosted language model.

This separation is intentional.

Computer vision provides the measurements, the controller determines the workflow, and cloud infrastructure supports deployment and integration.

The repository includes containerisation and EC2 setup resources, while full production hardening and deployment validation remain ongoing engineering priorities.

## Engineering and reliability

We designed WasteWatch AI around one principle:

**An environmental intelligence system must be able to explain its evidence before asking someone to act.**

### Evidence-driven decisions

Image-processing tools return structured measurements rather than unrestricted natural-language conclusions.

The agent uses those measurements to select subsequent operations.

### Observable reasoning

Each inspection generates a trace containing the invoked tool, relevant metrics, and the resulting decision.

This makes the inspection workflow reviewable and provides a foundation for debugging and evaluation.

### Controlled automation

The system can independently perform additional image-processing steps, but environmental findings remain subject to human confirmation.

### Safe interpretation

Disturbed soil, construction activity, mining, and waste disposal can exhibit overlapping visual characteristics.

WasteWatch AI therefore identifies candidate areas for investigation rather than claiming that satellite imagery alone proves illegal activity.

### Human oversight

Review cases have explicit states, and the backend supports guarded transitions for approval or dismissal.

The current implementation includes a reviewer-token mechanism; stronger identity management and production authentication are planned.

## Challenges we ran into

### 1. Distinguishing real changes from imaging artifacts

The first major challenge was the reliability of satellite image comparison.

Changes in lighting, cloud conditions, and alignment can create false positives that look convincing in a visual overlay.

We addressed this by separating quality assessment, image registration, and change localisation into measurable processing stages.

### 2. Making image alignment trustworthy

Finding a geometric transformation is not enough.

An overly flexible transformation may distort the scene or hide genuine changes.

We added geometric plausibility checks and a secondary ECC alignment path so the agent can react when the initial registration is unreliable.

### 3. Making autonomous actions technically meaningful

One of the most important design decisions concerned how an agent should respond to an uncertain region.

Simply enlarging an image does not introduce additional information.

We redesigned the inspection flow so its initial pass uses reduced-resolution imagery and its follow-up pass accesses the original pixels.

This helped us implement a meaningful form of active visual investigation.

### 4. Preventing AI from overclaiming

A changed surface is not necessarily an illegal waste site.

We deliberately separated visual measurements, disturbed-surface scoring, and final environmental interpretation.

This prevents heuristic scores from being presented as calibrated probabilities or verified violations.

### 5. Balancing autonomy with human control

We wanted the system to perform useful work independently without making unsupported decisions.

The resulting architecture gives the agent control over image-processing operations while reserving final confirmation for human review.

## Accomplishments we're proud of

We're particularly proud of implementing the foundation of a system where computer vision results directly influence the next processing action.

The current codebase contains:

- An OpenCV 5 vision engine for image quality assessment, registration, and change analysis.
- An agentic inspection controller that selects tools based on visual metrics.
- A native-resolution follow-up inspection path for uncertain regions.
- Structured execution traces explaining tool decisions.
- A FastAPI backend for running and retrieving inspections.
- A basic web interface for image upload and result visualisation.
- Human-review state handling.
- Automated smoke-test definitions and a preliminary evaluation pipeline.
- AWS deployment configuration and optional cloud integrations.

The most important outcome is the end-to-end inspection design:

**Satellite imagery → visual measurements → evidence-based actions → changed-region assessment → human verification.**

WasteWatch AI brings these capabilities together in a single, extensible system.

## What we learned

The most important lesson was that **reliable AI is not simply about producing an answer. It is about knowing which evidence supports that answer and what to do when the evidence is insufficient.**

We learned that computer vision and autonomous decision-making solve different but complementary problems.

OpenCV measures observable properties of imagery.

The inspection controller translates those measurements into subsequent processing actions.

Human reviewers provide context and judgment that visual measurements alone cannot establish.

We also learned that traceability, uncertainty handling, and meaningful follow-up actions are as important as the initial detection algorithm.

## What's next

Our next priorities are to complete the full web review workflow, validate cloud deployment, harden authentication and persistence, and produce reproducible evaluation results.

We also plan to add better satellite-specific cloud masking, geospatial metadata handling, multi-date monitoring, and more rigorous change-detection benchmarks.

Longer term, WasteWatch AI could support:

- Periodic monitoring of landfills and suspected dumping locations.
- Environmental change alerts for municipalities and regulators.
- Remote inspection prioritisation.
- Industrial and infrastructure land-disturbance monitoring.
- Integration with field-verification and environmental compliance platforms.

Our vision extends beyond identifying pixels that changed.

We want to help environmental teams understand where change is happening, investigate what it may mean, and make better decisions using traceable evidence.

**WasteWatch AI — From observing the Earth to acting on what matters.**

---

## Architecture (current build)

Two services:

- **Backend — FastAPI (`app/`)**: OpenCV 5 vision engine + the autonomous agent,
  plus real Sentinel-2 imagery. Key endpoints: `/geocode` (keyless OpenStreetMap
  place search), `/scenes` (real Sentinel-2 L2A search via Element84 Earth Search),
  `/inspect/scene/stream` (clips the chosen scenes to the AOI and streams the agent
  live over SSE), `/inspect/stream` (manual upload), `/alerts` (dashboard list),
  `/approve/{id}` (token-guarded human review). The browser never talks to it
  directly in production.
- **Frontend — Next.js 16 / React 19 / TypeScript / Tailwind (`frontend/`)**: the
  full 8-step journey — explore the globe, select a location (search + draw
  polygon/rectangle), choose real satellite dates, watch the agent analyse live,
  view results (Before / After / Change tabs, severity legend, stat tiles),
  explore regions with a before/after slider, review (confirm / dismiss / needs
  more info + comment), and track everything in a dashboard. It proxies `/api/*`
  to the backend (no CORS; SSE streams through).

### Real satellite imagery

Step 3 uses **real Sentinel-2 L2A** from the public AWS `sentinel-cogs` bucket via
Earth Search (STAC), with **no API key**. The backend windowed-reads the
true-colour COG and clips it to the AOI with rasterio/GDAL — only the needed
bytes are fetched. If rasterio is unavailable, the app degrades to manual
before/after upload.

## Run the full app

Two terminals (from the repo root):

```powershell
# 1) backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000

# 2) frontend
cd frontend
Copy-Item .env.local.example .env.local   # FASTAPI_ORIGIN=http://127.0.0.1:8000
npm install
npm run dev        # http://localhost:3000
```

## Known limitations (current build, honest ledger)

- **Per-inspection images are not archived.** Clips are written to fixed files
  (`out/in_before.png`, `in_after.png`, `change_map.png`) and overwritten each run,
  so the dashboard shows an inspection's *metadata and regions* but not its original
  imagery on revisit. Metadata/trace persist; per-id artifact storage is a TODO.
- **Cloud gate is an RGB heuristic**, not the Sentinel-2 Scene Classification (SCL)
  mask. The true-colour COG is an 8-bit visualisation, not raw reflectance.
- **`disturbed_surface` is a heuristic**, not a verified waste classification — the
  system flags *candidates* for human review, never confirmed violations.
- **Auth is a shared dev reviewer token.** No per-user identity, rate limiting, or
  production authentication yet. Set `REVIEWER_TOKEN` in production.
- **Deployment is not wired up** (frontend + backend are two services). Local run
  is fully working; App Runner / Vercel wiring is deferred.
