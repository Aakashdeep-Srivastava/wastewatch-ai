# app/ratelimit.py
# -----------------------------------------------------------------------------
# Cost-aware, highly-dynamic rate limiting for the WasteWatch backend.
#
# WHY: the backend runs on a small Nebius VM and its expensive path (NVIDIA
# Nemotron inference on Token Factory + Sentinel-2 COG egress) is the real money
# driver. We rate-limit BY COST AND RISK: tight on the paid/expensive endpoints,
# loose on free reads. Two independent controls:
#
#   1) Per-client token buckets, tiered by cost (expensive / moderate / cheap).
#   2) A global rolling 24h ceiling on paid AI calls. When exhausted, inspections
#      STILL RUN but skip the Nemotron brief (graceful CV-only degrade — reusing
#      the existing "no AI -> no brief, never mocked" contract). This caps spend
#      without taking the product down.
#
# "HIGHLY DYNAMIC": effective limits are not static. They are
#   effective = base(tier) * adaptive_factor
#   where adaptive_factor tightens automatically as the daily AI budget depletes
#   and as live inspection concurrency rises, then recovers. On top of that,
#   limits are tunable AT RUNTIME (no redeploy) via set_override(), surfaced by
#   the token-guarded /admin/limits endpoint, and observable via /limits.
#
# Single-process, in-memory (one small VM). HONEST LIMITATION: buckets + the AI
# budget are per-process, so with multiple replicas each gets its own share; a
# shared Redis store (storage_uri) would make them exact. Documented, not hidden.
# -----------------------------------------------------------------------------
import os
import time
import threading
from collections import deque

# ---- tier definitions: (env knob, default limit, period seconds) ------------
# expensive = runs CV + (maybe) paid Nemotron + Sentinel-2 egress.
# moderate  = calls external APIs with usage policies (OSM/Nominatim/Earth Search).
# cheap     = local reads (dashboard, health, trace).
_TIERS = {
    "expensive": {"env": "RL_EXPENSIVE_PER_HOUR", "default": 20.0, "period": 3600.0},
    "moderate":  {"env": "RL_MODERATE_PER_MIN",   "default": 30.0, "period": 60.0},
    "cheap":     {"env": "RL_CHEAP_PER_MIN",      "default": 240.0, "period": 60.0},
}

_lock = threading.Lock()
_buckets: dict[tuple[str, str], list[float]] = {}   # (tier, client) -> [tokens, last_ts]
_ai_calls: deque[float] = deque()                   # wall-clock ts of paid AI calls (24h window)
_active_inspections = 0                             # live concurrency gauge
_overrides: dict[str, float] = {}                   # runtime tuning (wins over env)

_AI_WINDOW = 86400.0                                 # 24h rolling window


def _enabled() -> bool:
    return os.getenv("RL_ENABLED", "on").lower() in ("1", "true", "on", "yes")


def _adapt_enabled() -> bool:
    return os.getenv("RL_ADAPT", "on").lower() in ("1", "true", "on", "yes")


def _cfg(key: str, default: float) -> float:
    """Runtime override wins over env wins over default — the 'dynamic' knob."""
    if key in _overrides:
        return _overrides[key]
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def ai_budget() -> float:
    return _cfg("AI_BUDGET_CALLS_PER_DAY", 500.0)


# ---- AI spend ceiling (the sustainability lever) ----------------------------
def _prune_ai(now: float) -> None:
    cutoff = now - _AI_WINDOW
    while _ai_calls and _ai_calls[0] < cutoff:
        _ai_calls.popleft()


def ai_used() -> int:
    with _lock:
        _prune_ai(time.time())
        return len(_ai_calls)


def ai_remaining() -> float:
    return max(0.0, ai_budget() - ai_used())


def ai_allowed() -> bool:
    """True while the rolling 24h paid-AI-call budget is not exhausted. When
    False, callers skip Nemotron and degrade to CV-only (never mock)."""
    if not _enabled():
        return True
    return ai_remaining() > 0


def record_ai_call() -> None:
    """Count one paid AI call against the rolling budget. Called by the nemotron
    layer right after a successful inference."""
    with _lock:
        _ai_calls.append(time.time())


# ---- adaptive factor --------------------------------------------------------
def adaptive_factor() -> float:
    """0.25..1.0 multiplier applied to the EXPENSIVE tier. Tightens as the daily
    AI budget depletes and as concurrency rises; recovers automatically."""
    if not _adapt_enabled():
        return 1.0
    budget = ai_budget()
    rem_ratio = (ai_remaining() / budget) if budget > 0 else 1.0
    budget_factor = 1.0 if rem_ratio >= 0.25 else (0.5 if rem_ratio >= 0.10 else 0.25)
    a = _active_inspections
    conc_factor = 1.0 if a < 4 else (0.5 if a < 8 else 0.25)
    return min(budget_factor, conc_factor)


def effective_limit(tier: str) -> float:
    base = _cfg(_TIERS[tier]["env"], _TIERS[tier]["default"])
    if tier == "expensive":
        return max(1.0, base * adaptive_factor())
    return base


# ---- concurrency gauge (context-manager friendly) ---------------------------
def inspection_started() -> None:
    global _active_inspections
    with _lock:
        _active_inspections += 1


def inspection_finished() -> None:
    global _active_inspections
    with _lock:
        _active_inspections = max(0, _active_inspections - 1)


# ---- the dynamic token bucket -----------------------------------------------
def check(tier: str, client: str) -> dict:
    """Consume one token for (tier, client) against the CURRENT effective rate.
    Returns {allowed, retry_after, limit, remaining}. Rate is recomputed every
    call, so env/override/adaptive changes take effect immediately."""
    if not _enabled() or tier not in _TIERS:
        return {"allowed": True, "retry_after": 0.0, "limit": 0.0, "remaining": 0.0}

    period = _TIERS[tier]["period"]
    capacity = effective_limit(tier)          # tokens per period (dynamic)
    refill = capacity / period if period > 0 else 0.0
    now = time.monotonic()

    with _lock:
        key = (tier, client)
        tokens, last = _buckets.get(key, [capacity, now])
        tokens = min(capacity, tokens + (now - last) * refill)   # cap at live capacity
        if tokens >= 1.0:
            tokens -= 1.0
            _buckets[key] = [tokens, now]
            return {"allowed": True, "retry_after": 0.0,
                    "limit": capacity, "remaining": tokens}
        retry = (1.0 - tokens) / refill if refill > 0 else _AI_WINDOW
        _buckets[key] = [tokens, now]
        return {"allowed": False, "retry_after": round(retry, 2),
                "limit": capacity, "remaining": tokens}


# ---- runtime tuning + observability -----------------------------------------
def set_override(key: str, value) -> None:
    """Live-tune a knob (RL_EXPENSIVE_PER_HOUR, RL_MODERATE_PER_MIN,
    RL_CHEAP_PER_MIN, AI_BUDGET_CALLS_PER_DAY). value None clears the override."""
    with _lock:
        if value is None:
            _overrides.pop(key, None)
        else:
            _overrides[key] = float(value)


def snapshot() -> dict:
    """Current effective state — powers GET /limits."""
    return {
        "enabled": _enabled(),
        "adaptive": _adapt_enabled(),
        "adaptive_factor": round(adaptive_factor(), 3),
        "active_inspections": _active_inspections,
        "tiers": {
            t: {"base_per_period": _cfg(_TIERS[t]["env"], _TIERS[t]["default"]),
                "period_seconds": _TIERS[t]["period"],
                "effective_limit": round(effective_limit(t), 2)}
            for t in _TIERS
        },
        "ai_budget": {
            "calls_per_day": ai_budget(),
            "used_24h": ai_used(),
            "remaining": ai_remaining(),
            "degraded_to_cv_only": not ai_allowed(),
        },
        "overrides": dict(_overrides),
    }
