# app/satellite.py
# -----------------------------------------------------------------------------
# REAL Sentinel-2 imagery for WasteWatch AI, keyless.
#
#  - search_scenes(): queries the Element84 Earth Search STAC API for Sentinel-2
#    L2A scenes over an AOI/date-range/cloud-cover (no API key).
#  - fetch_clip(): windowed-reads the scene's true-colour (TCI / "visual") Cloud
#    Optimized GeoTIFF straight from the public AWS "sentinel-cogs" bucket and
#    clips it to the AOI. Only the needed bytes are fetched (GDAL /vsicurl/).
#
# Honest limits: the true-colour COG is an 8-bit visualisation (not raw
# reflectance). It is REAL per-date Sentinel-2 imagery suitable for temporal
# change detection here; quantitative indices would use the raw band assets.
# If rasterio/GDAL is unavailable, AVAILABLE is False and callers fall back to
# manual before/after upload.
# -----------------------------------------------------------------------------
import os
import json
import urllib.request
import urllib.error

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
_UA = "WasteWatch-AI/1.0 (environmental monitoring demo)"

# GDAL tuning for fast partial reads of remote public COGs.
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("VSI_CACHE", "TRUE")

try:
    import rasterio  # noqa: F401
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    # A global PROJ_LIB/PROJ_DATA from another install (e.g. PostGIS) can shadow
    # rasterio's bundled PROJ database and break CRS lookups. Force rasterio's own.
    _RIO_DIR = os.path.dirname(rasterio.__file__)
    _PROJ_DATA = os.path.join(_RIO_DIR, "proj_data")
    _GDAL_DATA = os.path.join(_RIO_DIR, "gdal_data")
    if os.path.isdir(_PROJ_DATA):
        os.environ["PROJ_DATA"] = _PROJ_DATA
        os.environ["PROJ_LIB"] = _PROJ_DATA
    if os.path.isdir(_GDAL_DATA):
        os.environ["GDAL_DATA"] = _GDAL_DATA
    AVAILABLE = True
except Exception:   # pragma: no cover - environment without GDAL
    _PROJ_DATA = _GDAL_DATA = None
    AVAILABLE = False


def _post(url, payload, timeout=30):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def search_scenes(bbox, start, end, max_cloud=30, limit=12):
    """Find Sentinel-2 L2A scenes. bbox=[w,s,e,n] (EPSG:4326), start/end=YYYY-MM-DD.
    Returns newest-first scene dicts: id, date, datetime, cloud_cover, visual, thumbnail."""
    payload = {
        "collections": [COLLECTION],
        "bbox": list(bbox),
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": float(max_cloud)}},
        "limit": int(limit),
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    fc = _post(STAC_URL, payload)
    scenes = []
    for f in fc.get("features", []):
        p = f.get("properties", {})
        a = f.get("assets", {})
        vis = a.get("visual") or a.get("visual-10m")
        if not vis or not vis.get("href"):
            continue
        thumb = a.get("thumbnail") or a.get("overview") or {}
        scenes.append({
            "id": f.get("id"),
            "datetime": p.get("datetime"),
            "date": (p.get("datetime") or "")[:10],
            "cloud_cover": round(float(p.get("eo:cloud_cover", 0.0)), 1),
            "resolution_m": 10,
            "visual": vis["href"],
            "thumbnail": thumb.get("href"),
        })
    return scenes


def fetch_clip(bbox, visual_href, out_path, max_dim=1024, out_size=None):
    """Clip a scene's true-colour COG to the AOI bbox and save as PNG.
    Returns (out_path, (width, height)). out_size forces a fixed output size so
    a T2 image can match T1 exactly (cleaner change detection)."""
    if not AVAILABLE:
        raise RuntimeError("rasterio/GDAL not available for COG clipping")
    import numpy as np
    import cv2 as cv
    import rasterio

    w, s, e, n = bbox
    url = visual_href if visual_href.startswith("/vsicurl/") else "/vsicurl/" + visual_href
    env_kw = {"AWS_NO_SIGN_REQUEST": "YES", "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}
    if _PROJ_DATA:
        env_kw["PROJ_DATA"] = _PROJ_DATA
    if _GDAL_DATA:
        env_kw["GDAL_DATA"] = _GDAL_DATA
    with rasterio.Env(**env_kw), rasterio.open(url) as ds:
        left, bottom, right, top = transform_bounds("EPSG:4326", ds.crs, w, s, e, n)
        win = from_bounds(left, bottom, right, top, ds.transform)
        if out_size:
            out_w, out_h = int(out_size[0]), int(out_size[1])
        else:
            scale = min(1.0, max_dim / max(win.width, win.height, 1.0))
            out_w = max(1, round(win.width * scale))
            out_h = max(1, round(win.height * scale))
        data = ds.read([1, 2, 3], window=win, out_shape=(3, out_h, out_w),
                       boundless=True, fill_value=0)
    rgb = np.transpose(data, (1, 2, 0)).astype(np.uint8)
    bgr = cv.cvtColor(rgb, cv.COLOR_RGB2BGR)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cv.imwrite(out_path, bgr)
    return out_path, (out_w, out_h)
