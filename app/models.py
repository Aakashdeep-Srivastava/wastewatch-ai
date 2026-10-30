# app/models.py
# -----------------------------------------------------------------------------
# Pydantic request/response models for the WasteWatch API.
#
# DESIGN DECISION (deliberate, see PRD §4 "AI asks, humans decide"):
#   - Fields WE control and compute deterministically (CV metrics, blobs, trace,
#     image size, AOI, review state) are STRONGLY typed.
#   - Payloads produced by an LLM or an external open-data source (the Nemotron
#     `brief`, the `adviser` note, the `enrichment` block) are kept as free-form
#     dicts. We do NOT over-constrain model/third-party output — the frontend
#     reads only known keys, and a strict schema here would turn a harmless extra
#     key or a reshaped upstream response into a 500 on the critical path.
# -----------------------------------------------------------------------------
from typing import Any

from pydantic import BaseModel, Field

Bbox = list[float]  # [west, south, east, north], EPSG:4326


# ----- request models --------------------------------------------------------
class SceneInspectReq(BaseModel):
    """REAL Sentinel-2 scene inspection request (POST /inspect/scene/stream)."""
    aoi: list[float]
    t1_visual: str
    t2_visual: str
    alt_visual: str | None = None
    location: str | None = None
    area_km2: float | None = None
    t1_date: str | None = None
    t2_date: str | None = None


# ----- shared building blocks (strongly typed: WE compute these) -------------
class ImageSize(BaseModel):
    w: int
    h: int


class Dates(BaseModel):
    t1: str | None = None
    t2: str | None = None


class Blob(BaseModel):
    """A detected change region in BEFORE full-resolution pixel coords."""
    x: int
    y: int
    w: int
    h: int
    area: int
    disturbed_surface: float


class TraceStep(BaseModel):
    """One perceive->decide->act step emitted by the agent."""
    step: int
    tool: str
    metric: dict[str, Any] = Field(default_factory=dict)
    decision: str
    t: float


# ----- the inspection record -------------------------------------------------
class InspectRecord(BaseModel):
    """The stored/returned result of one inspection. CV fields are strict;
    AI/enrichment payloads are free-form dicts (see module docstring)."""
    id: str
    status: str
    candidate_type: str | None = None
    display: str = ""
    change_score: float = 0.0
    disturbed_surface: float = 0.0
    blobs: list[Blob] = Field(default_factory=list)
    num_regions: int = 0
    image_size: ImageSize
    aoi: Bbox | None = None
    location: str | None = None
    area_km2: float | None = None
    dates: Dates | None = None
    source: str = "upload"
    created: int = 0
    updated: int | None = None
    comment: str | None = None
    # free-form (LLM / external open data) — intentionally not over-typed:
    adviser: dict[str, Any] | None = None
    enrichment: dict[str, Any] | None = None
    brief: dict[str, Any] | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)


# ----- list / dashboard views ------------------------------------------------
class AlertListItem(BaseModel):
    id: str | None = None
    status: str | None = None
    location: str | None = None
    created: int | None = None
    updated: int | None = None
    num_regions: int = 0
    change_score: float | None = None
    area_km2: float | None = None
    dates: Dates | None = None
    source: str | None = None


class AlertsResponse(BaseModel):
    alerts: list[AlertListItem]


# ----- scenes / geocode ------------------------------------------------------
class Scene(BaseModel):
    # lenient on purpose: Earth Search payloads vary; the frontend reads these
    # keys and tolerates missing ones.
    id: str
    date: str | None = None
    datetime: str | None = None
    cloud_cover: float | None = None
    resolution_m: float | None = None
    visual: str
    thumbnail: str | None = None


class ScenesResponse(BaseModel):
    scenes: list[Scene]


class GeocodeResult(BaseModel):
    name: str | None = None
    lat: float
    lon: float
    bbox: Bbox | None = None


class GeocodeResponse(BaseModel):
    results: list[GeocodeResult]


# ----- misc ------------------------------------------------------------------
class HealthResponse(BaseModel):
    ok: bool
    opencv_version: str
    service: str
    ai: dict[str, Any]  # nemotron.provider_info() — provider-shaped, free-form


class ApproveResult(BaseModel):
    ok: bool
    status: str
    reason: str


class LimitOverrides(BaseModel):
    """Runtime rate-limit tuning (POST /admin/limits). Any field left null is
    unchanged; send a value to override, or clear via the endpoint semantics."""
    RL_EXPENSIVE_PER_HOUR: float | None = None
    RL_MODERATE_PER_MIN: float | None = None
    RL_CHEAP_PER_MIN: float | None = None
    AI_BUDGET_CALLS_PER_DAY: float | None = None
