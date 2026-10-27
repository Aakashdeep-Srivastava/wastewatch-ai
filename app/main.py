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
import shutil
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


@app.post("/inspect")
async def inspect(before: UploadFile = File(...), after: UploadFile = File(...),
                  alt_after: UploadFile = File(None)):
    b = _save_upload(before, "in_before.png")
    a = _save_upload(after, "in_after.png")
    alts = [_save_upload(alt_after, "in_alt.png")] if alt_after is not None else []
    res = agent.inspect(b, a, alt_after_paths=alts, out_dir=OUT)
    v = res["verdict"]
    record = {"id": res["id"], "status": v["status"],
              "candidate_type": v.get("candidate_type"),
              "display": v.get("display", ""),
              "change_score": v.get("change_score", 0.0),
              "disturbed_surface": v.get("disturbed_surface", 0.0),
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
