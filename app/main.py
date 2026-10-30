# app/main.py
# -----------------------------------------------------------------------------
# WasteWatch AI web server.
#   GET  /health              -> status + REAL cv2.__version__
#   GET  /map/config          -> machine-readable map capabilities (for agents)
#   GET  /agent/ui-schema     -> streaming-event + UI-component vocabulary
#   GET  /geocode?q=          -> keyless place search (OpenStreetMap Nominatim)
#   GET  /scenes?bbox=&start= -> real Sentinel-2 L2A scene search (Earth Search)
#   POST /inspect             -> run the agent loop once, return the full result
#   POST /inspect/stream      -> SSE: stream each agent step live, then a UI spec
#   POST /inspect/scene/stream-> SSE: clip real Sentinel-2 scenes, then stream
#   GET  /alerts              -> all inspections (dashboard list)
#   GET  /trace/{id}          -> stored alert + full step trace
#   POST /approve/{id}        -> REVIEWER-TOKEN protected; guarded state change
# Human control is real: approval needs a token AND a legal state transition.
#
# The streaming endpoint + server-emitted UI spec are an A2UI / AG-UI *inspired*
# design (not the official runtimes): the agent streams what it is doing, then
# describes the inspection panel as structured components the browser renders.
# -----------------------------------------------------------------------------
import os
import json
import time
import queue
import threading
import urllib.parse
import urllib.request
import cv2 as cv

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, store, satellite, nemotron

OUT = os.getenv("ORBIT_OUT", "out")
os.makedirs(OUT, exist_ok=True)
STATIC = os.path.join(os.path.dirname(__file__), "static")
LOGO = os.path.join(STATIC, "logo.png")
MAX_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))   # 20 MB/file
MAX_PIXELS = int(os.getenv("MAX_PIXELS", str(40_000_000)))             # ~40 MP
REVIEWER_TOKEN = os.getenv("REVIEWER_TOKEN", "dev-reviewer-token")      # set in prod!

app = FastAPI(title="WasteWatch AI")
app.mount("/out", StaticFiles(directory=OUT), name="out")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(LOGO)


@app.get("/")
def home():
    # The browser UI is the separate Next.js frontend. This backend serves the
    # API only; it is self-describing here for humans and agents.
    return {"service": "wastewatch-ai", "ui": "Next.js frontend (separate service)",
            "endpoints": ["/health", "/map/config", "/agent/ui-schema",
                          "/inspect", "/inspect/stream", "/trace/{id}",
                          "/approve/{id}"]}


@app.get("/health")
def health():
    return {"ok": True, "opencv_version": cv.__version__, "service": "wastewatch-ai",
            "ai": nemotron.provider_info()}


# -----------------------------------------------------------------------------
# /map/config: machine-readable map capabilities. Lets an agent discover the
# basemap layers, fly-to presets, the AOI format, and the inspection contract
# without scraping the HTML. Basemaps are historical composites (context only);
# real temporal change detection uses the uploaded Sentinel-2 pair, not tiles.
# -----------------------------------------------------------------------------
@app.get("/map/config")
def map_config():
    return {
        "projection": "globe",
        "default_view": {"center": [72.0, 18.0], "zoom": 1.4},
        "layers": [
            {"id": "earth", "name": "NASA Blue Marble", "type": "raster",
             "source": "NASA EOSDIS GIBS",
             "tiles": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
                      "BlueMarble_NextGeneration/default/2004-01-01/"
                      "GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
             "maxzoom": 8, "role": "earth-scale context"},
            {"id": "sentinel", "name": "Sentinel-2 Cloudless 2016", "type": "raster",
             "source": "EOX (CC BY 4.0), modified Copernicus Sentinel data",
             "tiles": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/"
                      "default/GoogleMapsCompatible/{z}/{y}/{x}.jpg",
             "maxzoom": 14, "role": "zoomed-in satellite basemap"},
        ],
        "presets": [
            {"name": "Goa", "center": [73.95, 15.5], "zoom": 10},
            {"name": "Earth", "center": [70.0, 18.0], "zoom": 1.4},
        ],
        "aoi": {"format": "bbox", "order": "[west, south, east, north]",
                "crs": "EPSG:4326"},
        "inspect": {"endpoint": "/inspect", "method": "POST",
                    "fields": ["before (file)", "after (file)",
                               "alt_after (file, optional)",
                               "aoi (json [w,s,e,n], optional)"],
                    "returns": "status, change_score, blobs[pixel coords], "
                               "image_size{w,h}, aoi, trace, artifacts"},
        "note": "Basemap tiles are fixed historical composites for navigation "
                "and context only; they are NOT a valid source for temporal "
                "change detection. Supply real before/after Sentinel-2 "
                "observations to /inspect for analysis.",
    }


def _save_upload(up, name):
    data = up.file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"{up.filename} exceeds {MAX_BYTES} bytes")
    path = os.path.join(OUT, name)
    with open(path, "wb") as f:
        f.write(data)
    img = cv.imread(path, cv.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, f"{up.filename} is not a decodable image")
    if img.shape[0] * img.shape[1] > MAX_PIXELS:
        raise HTTPException(413, f"{up.filename} exceeds {MAX_PIXELS} pixels")
    return path


def _parse_aoi(aoi):
    """Validate an optional AOI bbox [west, south, east, north] (EPSG:4326)."""
    if not aoi:
        return None
    try:
        box = json.loads(aoi) if isinstance(aoi, str) else aoi
        w, s, e, n = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except Exception:
        raise HTTPException(400, "aoi must be JSON [west, south, east, north]")
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= 90 and -90 <= n <= 90):
        raise HTTPException(400, "aoi coordinates out of range")
    return [w, s, e, n]


def _build_record(res, image_size, box, meta=None):
    """Shape the agent result into the stored/returned record (blobs in BEFORE
    full-resolution pixel coords; image_size + aoi let the client map to geo).
    meta carries dashboard context: location, area_km2, dates."""
    v = res["verdict"]
    meta = meta or {}
    blobs = v.get("blobs", [])
    return {"id": res["id"], "status": v["status"],
            "candidate_type": v.get("candidate_type"),
            "display": v.get("display", ""),
            "change_score": v.get("change_score", 0.0),
            "disturbed_surface": v.get("disturbed_surface", 0.0),
            "blobs": blobs,
            "num_regions": len(blobs),
            "image_size": image_size,
            "aoi": box,
            "location": meta.get("location"),
            "area_km2": meta.get("area_km2"),
            "dates": meta.get("dates"),
            "source": meta.get("source", "upload"),
            "created": int(time.time()),
            "adviser": v.get("adviser"),
            "enrichment": v.get("enrichment"),
            "brief": v.get("brief"),
            "trace": res["trace"],
            "artifacts": {k: "/" + p.replace("\\", "/")
                          for k, p in res["artifacts"].items()}}


def _ui_spec(record):
    """A2UI-inspired component spec for the inspection panel. The agent describes
    the interface; the browser renders it. Actions appear only when the state is
    human-reviewable, so the UI can never offer an illegal approval."""
    status = record["status"]
    reviewable = status in ("PENDING_REVIEW", "NEEDS_REVIEW")
    children = [
        {"type": "badge", "status": status,
         "label": status.replace("_", " ").title()},
        {"type": "metric", "label": "Change score",
         "value": round(record.get("change_score", 0.0), 3)},
        {"type": "meter", "label": "Disturbed surface",
         "value": round(record.get("disturbed_surface", 0.0), 3)},
    ]
    if record.get("display"):
        children.append({"type": "text", "variant": "muted",
                         "value": record["display"]})
    brief = record.get("brief")
    if brief:
        children.append({"type": "brief", "title": "Nemotron intelligence brief",
                         "provider": "NVIDIA Nemotron on Nebius Token Factory",
                         "headline": brief.get("headline"),
                         "likely_cause": brief.get("likely_cause"),
                         "legality": brief.get("legality"),
                         "severity": brief.get("severity"),
                         "recommended_action": brief.get("recommended_action"),
                         "confidence": brief.get("confidence"),
                         "rationale": brief.get("rationale"),
                         "model": brief.get("model")})
    enr = record.get("enrichment")
    if enr:
        fac = enr.get("nearest_waste_facility") or {}
        chips = []
        if fac.get("distance_m") is not None:
            chips.append({"label": "Nearest permitted site",
                          "value": f"{fac['distance_m']} m ({fac.get('kind')})"})
        elif fac.get("note"):
            chips.append({"label": "Permitted sites nearby", "value": fac["note"]})
        aq = enr.get("air_quality") or {}
        if aq.get("pm2_5") is not None:
            chips.append({"label": "PM2.5", "value": f"{aq['pm2_5']} {aq.get('units')}"})
        news = enr.get("news") or {}
        if news.get("results"):
            chips.append({"label": "Local reports", "value": f"{len(news['results'])} found"})
        if chips:
            children.append({"type": "enrichment",
                             "title": "Global environmental context", "chips": chips})
    blobs = record.get("blobs") or []
    if blobs:
        children.append({"type": "cards", "title": f"Detections ({len(blobs)})",
                         "items": [{"title": f"#{i + 1}", "area": b.get("area"),
                                    "ds": b.get("disturbed_surface")}
                                   for i, b in enumerate(blobs)]})
    if record.get("adviser"):
        children.append({"type": "text", "variant": "muted",
                         "value": "Adviser (non-authoritative): "
                                  + json.dumps(record["adviser"])})
    children.append({"type": "timeline", "title": "Agent trace",
                     "steps": record.get("trace", [])})
    if reviewable:
        children.append({"type": "actions", "items": [
            {"id": "approve", "label": "Approve", "kind": "primary"},
            {"id": "dismiss", "label": "Dismiss", "kind": "ghost"}]})
    return {"type": "panel", "title": f"Inspection {record['id']}",
            "alertId": record["id"], "children": children}


def _prepare_inputs(before, after, alt_after, aoi):
    box = _parse_aoi(aoi)
    b = _save_upload(before, "in_before.png")
    a = _save_upload(after, "in_after.png")
    alts = [_save_upload(alt_after, "in_alt.png")] if alt_after is not None else []
    bimg = cv.imread(b, cv.IMREAD_COLOR)
    image_size = {"w": int(bimg.shape[1]), "h": int(bimg.shape[0])}
    return b, a, alts, image_size, box


def _sse(payload):
    return "data: " + json.dumps(payload) + "\n\n"


def _stream_inspection(b, a, alts, image_size, box, meta=None):
    """Shared SSE machinery: run the agent in a thread, stream each step, then
    the result record and the agent-generated UI spec."""
    q = queue.Queue()

    def emit(entry):
        q.put({"type": "step", **entry})

    def work():
        try:
            res = agent.inspect(b, a, alt_after_paths=alts, out_dir=OUT, emit=emit,
                                aoi=box, location=(meta or {}).get("location"),
                                dates=(meta or {}).get("dates"))
            record = _build_record(res, image_size, box, meta)
            store.put_alert(record)
            q.put({"type": "result", "record": record})
            q.put({"type": "ui", "component": _ui_spec(record)})
        except Exception as exc:                       # noqa: BLE001 (stream it)
            q.put({"type": "error", "message": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def gen():
        yield _sse({"type": "start", "image_size": image_size, "aoi": box})
        while True:
            ev = q.get()
            if ev is None:
                break
            yield _sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/inspect")
async def inspect(before: UploadFile = File(...), after: UploadFile = File(...),
                  alt_after: UploadFile = File(None), aoi: str = Form(None),
                  location: str = Form(None), area_km2: float = Form(None)):
    b, a, alts, image_size, box = _prepare_inputs(before, after, alt_after, aoi)
    res = agent.inspect(b, a, alt_after_paths=alts, out_dir=OUT,
                        aoi=box, location=location)
    meta = {"location": location, "area_km2": area_km2, "source": "upload"}
    record = _build_record(res, image_size, box, meta)
    store.put_alert(record)
    return JSONResponse(record)


@app.post("/inspect/stream")
async def inspect_stream(before: UploadFile = File(...),
                         after: UploadFile = File(...),
                         alt_after: UploadFile = File(None),
                         aoi: str = Form(None),
                         location: str = Form(None),
                         area_km2: float = Form(None)):
    """SSE stream for an UPLOADED before/after pair."""
    b, a, alts, image_size, box = _prepare_inputs(before, after, alt_after, aoi)
    meta = {"location": location, "area_km2": area_km2, "source": "upload"}
    return _stream_inspection(b, a, alts, image_size, box, meta)


class SceneInspectReq(BaseModel):
    aoi: list[float]
    t1_visual: str
    t2_visual: str
    alt_visual: str | None = None
    location: str | None = None
    area_km2: float | None = None
    t1_date: str | None = None
    t2_date: str | None = None


@app.post("/inspect/scene/stream")
def inspect_scene_stream(req: SceneInspectReq):
    """SSE stream for REAL Sentinel-2 scenes: clip both dates to the AOI, then
    run the same streaming agent."""
    if not satellite.AVAILABLE:
        raise HTTPException(503, "satellite imagery unavailable (rasterio not installed)")
    box = _parse_aoi(req.aoi)
    if box is None:
        raise HTTPException(400, "aoi required")
    try:
        b, (W, H) = satellite.fetch_clip(box, req.t1_visual,
                                         os.path.join(OUT, "in_before.png"))
        a, _ = satellite.fetch_clip(box, req.t2_visual,
                                    os.path.join(OUT, "in_after.png"), out_size=(W, H))
        alts = []
        if req.alt_visual:
            alt, _ = satellite.fetch_clip(box, req.alt_visual,
                                          os.path.join(OUT, "in_alt.png"), out_size=(W, H))
            alts = [alt]
    except Exception as exc:                            # noqa: BLE001
        raise HTTPException(502, f"failed to fetch imagery: {exc}")
    meta = {"location": req.location, "area_km2": req.area_km2, "source": "sentinel-2",
            "dates": {"t1": req.t1_date, "t2": req.t2_date}}
    return _stream_inspection(b, a, alts, {"w": W, "h": H}, box, meta)


@app.get("/scenes")
def scenes(bbox: str, start: str, end: str, max_cloud: float = 30.0):
    """Search real Sentinel-2 L2A scenes over an AOI. bbox = 'west,south,east,north'."""
    if not satellite.AVAILABLE:
        raise HTTPException(503, "satellite imagery unavailable (rasterio not installed)")
    try:
        parts = [float(x) for x in bbox.split(",")]
    except Exception:
        raise HTTPException(400, "bbox must be 'west,south,east,north'")
    box = _parse_aoi(parts)
    try:
        return {"scenes": satellite.search_scenes(box, start, end, max_cloud=max_cloud)}
    except Exception as exc:                            # noqa: BLE001
        raise HTTPException(502, f"scene search failed: {exc}")


@app.get("/geocode")
def geocode(q: str):
    """Keyless place search via OpenStreetMap Nominatim."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 5})
    gr = urllib.request.Request(url, headers={"User-Agent": "WasteWatch-AI/1.0 (demo)"})
    try:
        with urllib.request.urlopen(gr, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as exc:                            # noqa: BLE001
        raise HTTPException(502, f"geocoding failed: {exc}")
    out = []
    for d in data:
        bb = d.get("boundingbox")
        out.append({
            "name": d.get("display_name"),
            "lat": float(d["lat"]), "lon": float(d["lon"]),
            # Nominatim bbox is [south, north, west, east]; convert to [w,s,e,n]
            "bbox": [float(bb[2]), float(bb[0]), float(bb[3]), float(bb[1])] if bb else None,
        })
    return {"results": out}


@app.get("/alerts")
def alerts():
    """All inspections for the dashboard (trimmed list view)."""
    items = store.list_alerts()
    return {"alerts": [{
        "id": r.get("id"), "status": r.get("status"),
        "location": r.get("location"), "created": r.get("created"),
        "updated": r.get("updated"),
        "num_regions": r.get("num_regions", len(r.get("blobs") or [])),
        "change_score": r.get("change_score"), "area_km2": r.get("area_km2"),
        "dates": r.get("dates"), "source": r.get("source"),
    } for r in items]}


@app.get("/agent/ui-schema")
def ui_schema():
    """Vocabulary for the streaming agentic UI, so agents know what to expect."""
    return {
        "transport": "SSE over POST /inspect/stream (data: <json>\\n\\n)",
        "events": {
            "start": "{image_size:{w,h}, aoi:[w,s,e,n]|null}",
            "step": "{step, tool, metric, decision, t}  (one per agent action)",
            "result": "{record}  (same shape as POST /inspect)",
            "ui": "{component}  (render spec, see components)",
            "error": "{message}",
        },
        "components": {
            "panel": "{title, alertId, children[]}",
            "badge": "{status, label}",
            "metric": "{label, value}",
            "meter": "{label, value(0..1)}",
            "text": "{value, variant?}",
            "cards": "{title, items[{title, area, ds}]}",
            "timeline": "{title, steps[{tool, metric, decision}]}",
            "actions": "{items[{id, label, kind}]}  (ids: approve|dismiss)",
        },
        "note": "A2UI/AG-UI-inspired, not the official runtimes. Actions appear "
                "only for human-reviewable states; approval still requires the "
                "reviewer token at POST /approve/{id}.",
    }


@app.get("/trace/{alert_id}")
def trace(alert_id: str):
    return JSONResponse(store.get_alert(alert_id) or {"error": "not found"})


@app.post("/approve/{alert_id}")
def approve(alert_id: str, decision: str = Form(...), comment: str = Form(None),
            x_reviewer_token: str = Header(None)):
    # human control: must present the reviewer token (authorized analyst)
    if x_reviewer_token != REVIEWER_TOKEN:
        raise HTTPException(401, "reviewer token required")
    mapping = {"approve": "CONFIRMED", "dismiss": "DISMISSED",
               "needs_info": "NEEDS_MORE_INFO"}
    new = mapping.get(decision)
    if not new:
        raise HTTPException(400, "decision must be approve | dismiss | needs_info")
    result = store.set_status(alert_id, new, comment=comment)
    if not result["ok"]:
        raise HTTPException(409, result["reason"])
    return JSONResponse(result)
