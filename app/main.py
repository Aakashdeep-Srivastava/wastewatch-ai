# app/main.py
# -----------------------------------------------------------------------------
# WasteWatch AI web server.
#   GET  /health              -> status + REAL cv2.__version__
#   POST /inspect             -> run the agent loop (public, rate/size limited)
#   GET  /trace/{id}          -> stored alert + full step trace
#   POST /approve/{id}        -> REVIEWER-TOKEN protected; guarded state change
# Human control is real: approval needs a token AND a legal state transition.
# -----------------------------------------------------------------------------
import os
import json
import cv2 as cv

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import agent, store

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


@app.get("/", response_class=HTMLResponse)
def home():
    with open(os.path.join(os.path.dirname(__file__), "templates", "index.html")) as f:
        return f.read()


@app.get("/health")
def health():
    return {"ok": True, "opencv_version": cv.__version__, "service": "wastewatch-ai"}


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


@app.post("/inspect")
async def inspect(before: UploadFile = File(...), after: UploadFile = File(...),
                  alt_after: UploadFile = File(None), aoi: str = Form(None)):
    box = _parse_aoi(aoi)
    b = _save_upload(before, "in_before.png")
    a = _save_upload(after, "in_after.png")
    alts = [_save_upload(alt_after, "in_alt.png")] if alt_after is not None else []
    # detection blobs are in BEFORE-image full-resolution pixel coordinates
    bimg = cv.imread(b, cv.IMREAD_COLOR)
    image_size = {"w": int(bimg.shape[1]), "h": int(bimg.shape[0])}
    res = agent.inspect(b, a, alt_after_paths=alts, out_dir=OUT)
    v = res["verdict"]
    record = {"id": res["id"], "status": v["status"],
              "candidate_type": v.get("candidate_type"),
              "display": v.get("display", ""),
              "change_score": v.get("change_score", 0.0),
              "disturbed_surface": v.get("disturbed_surface", 0.0),
              "blobs": v.get("blobs", []),
              "image_size": image_size,
              "aoi": box,
              "adviser": v.get("adviser"),
              "trace": res["trace"],
              "artifacts": {k: "/" + p.replace("\\", "/")
                            for k, p in res["artifacts"].items()}}
    store.put_alert(record)
    return JSONResponse(record)


@app.get("/trace/{alert_id}")
def trace(alert_id: str):
    return JSONResponse(store.get_alert(alert_id) or {"error": "not found"})


@app.post("/approve/{alert_id}")
def approve(alert_id: str, decision: str = Form(...),
            x_reviewer_token: str = Header(None)):
    # human control: must present the reviewer token (authorized analyst)
    if x_reviewer_token != REVIEWER_TOKEN:
        raise HTTPException(401, "reviewer token required")
    new = "CONFIRMED" if decision == "approve" else "DISMISSED"
    result = store.set_status(alert_id, new)
    if not result["ok"]:
        raise HTTPException(409, result["reason"])
    return JSONResponse(result)
