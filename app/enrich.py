# app/enrich.py
# -----------------------------------------------------------------------------
# GLOBAL ENVIRONMENTAL CONTEXT for a detected change. Given the AOI, ask the
# open public record "what is officially known here?" so Nemotron can reason
# about legality and severity instead of guessing from pixels alone.
#
# Sources (work worldwide -> USA, Europe, India identically):
#   OpenStreetMap Overpass   nearest mapped/permitted waste facility + distance
#                            (keyless). The core legality signal: a change far
#                            from any permitted site leans illegal.
#   Open-Meteo Air Quality   PM2.5 / PM10 near the site (keyless, global) -
#                            dumping & burning correlate with AQ spikes.
#   Tavily Search            live news / complaints near the location
#                            (needs TAVILY_API_KEY; graceful if absent).
#
# Everything degrades to None on failure; the pipeline never blocks on context.
# Regional "deep" layers (US EPA ECHO/LMOP, EU EEA E-PRTR, India CPCB) are
# documented in the README as drop-in extensions of the same contract.
# -----------------------------------------------------------------------------
import concurrent.futures
import json
import math
import os
import urllib.parse
import urllib.request

UA = {"User-Agent": "WasteWatch-AI/1.0 (hackathon demo)"}
# Multiple Overpass mirrors: public instances are rate-limited / occasionally
# slow, so we race through them with a short per-try timeout and never let a
# stalled mirror block the live inspection stream.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
OVERPASS_TIMEOUT = float(os.getenv("OVERPASS_TIMEOUT", "8"))
ENRICH_DEADLINE = float(os.getenv("ENRICH_DEADLINE", "10"))  # overall cap (s)
AIRQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TAVILY_URL = "https://api.tavily.com/search"


def _centroid(aoi):
    """aoi = [west, south, east, north] -> (lat, lon)."""
    w, s, e, n = aoi
    return (s + n) / 2.0, (w + e) / 2.0


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def nearest_waste_facility(lat, lon, radius_m=6000):
    """Nearest mapped waste/landfill facility from OpenStreetMap (keyless).

    Returns {name, kind, distance_m, lat, lon, count_within_radius} or None.
    """
    q = f"""
[out:json][timeout:25];
(
  nwr(around:{radius_m},{lat},{lon})["landuse"="landfill"];
  nwr(around:{radius_m},{lat},{lon})["amenity"="waste_disposal"];
  nwr(around:{radius_m},{lat},{lon})["amenity"="waste_transfer_station"];
  nwr(around:{radius_m},{lat},{lon})["man_made"="wastewater_plant"];
  nwr(around:{radius_m},{lat},{lon})["waste"];
  nwr(around:{radius_m},{lat},{lon})["industrial"="scrap_yard"];
);
out center tags 60;
""".strip()
    body = urllib.parse.urlencode({"data": q}).encode()
    els = None
    for url in OVERPASS_URLS:
        try:
            data = urllib.request.urlopen(
                urllib.request.Request(url, data=body, headers=UA),
                timeout=OVERPASS_TIMEOUT)
            els = json.loads(data.read()).get("elements", [])
            break
        except Exception:
            continue
    if els is None:
        return None
    best, best_d, count = None, float("inf"), 0
    for el in els:
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if c.get("lat") is None or c.get("lon") is None:
            continue
        count += 1
        d = _haversine_m(lat, lon, c["lat"], c["lon"])
        if d < best_d:
            tags = el.get("tags", {})
            kind = (tags.get("landuse") or tags.get("amenity")
                    or tags.get("man_made") or tags.get("waste")
                    or tags.get("industrial") or "waste_feature")
            best_d = d
            best = {"name": tags.get("name", "(unnamed facility)"), "kind": kind,
                    "distance_m": round(d), "lat": c["lat"], "lon": c["lon"]}
    if best is None:
        return {"name": None, "kind": None,
                "distance_m": None, "count_within_radius": 0,
                "note": f"no mapped waste facility within {radius_m} m"}
    best["count_within_radius"] = count
    return best


def air_quality(lat, lon):
    """Current PM2.5 / PM10 near the site via Open-Meteo (keyless, global)."""
    url = AIRQ_URL + "?" + urllib.parse.urlencode(
        {"latitude": round(lat, 4), "longitude": round(lon, 4),
         "current": "pm10,pm2_5"})
    try:
        cur = _get_json(url).get("current", {})
    except Exception:
        return None
    if not cur:
        return None
    return {"pm2_5": cur.get("pm2_5"), "pm10": cur.get("pm10"),
            "units": "ug/m3", "time": cur.get("time")}


def local_news(location, lat=None, lon=None, max_results=3):
    """Recent dumping / landfill reports near the place via Tavily (optional)."""
    key = os.getenv("TAVILY_API_KEY")
    if not key or not location:
        return None
    query = f"illegal dumping OR landfill OR waste site near {location}"
    body = json.dumps({"api_key": key, "query": query,
                       "max_results": max_results, "search_depth": "basic",
                       "topic": "news"}).encode()
    try:
        req = urllib.request.Request(
            TAVILY_URL, data=body,
            headers={**UA, "Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception:
        return None
    hits = [{"title": r.get("title"), "url": r.get("url")}
            for r in res.get("results", [])[:max_results]]
    return {"query": query, "results": hits} if hits else None


def gather(aoi, location=None):
    """Collect all available context for an AOI. The three sources run
    CONCURRENTLY under one wall-clock deadline, so total latency is the slowest
    single source (Overpass), not their sum, and a stalled source never blocks
    the live inspection stream. Returns whatever finished in time."""
    if not aoi:
        return None
    lat, lon = _centroid(aoi)
    ctx = {"centroid": {"lat": round(lat, 5), "lon": round(lon, 5)}}
    jobs = {
        "nearest_waste_facility": lambda: nearest_waste_facility(lat, lon),
        "air_quality": lambda: air_quality(lat, lon),
        "news": lambda: local_news(location, lat, lon),
    }
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    futs = {pool.submit(fn): key for key, fn in jobs.items()}
    try:
        for fut in concurrent.futures.as_completed(futs, timeout=ENRICH_DEADLINE):
            key = futs[fut]
            try:
                val = fut.result()
            except Exception:                       # noqa: BLE001
                val = None
            if val is not None:
                ctx[key] = val
    except concurrent.futures.TimeoutError:
        pass  # keep whatever finished before the deadline
    # Return at the deadline; don't block on a straggler (e.g. a slow Overpass
    # mirror). The pending thread drains harmlessly in the background.
    pool.shutdown(wait=False)
    return ctx
