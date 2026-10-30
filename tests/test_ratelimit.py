# tests/test_ratelimit.py
# Cost-aware dynamic rate-limiter tests. Run: python -m pytest -q
from app import ratelimit


def _reset():
    """Clear all in-memory limiter state between assertions."""
    ratelimit._buckets.clear()
    ratelimit._ai_calls.clear()
    ratelimit._overrides.clear()
    ratelimit._active_inspections = 0


def test_expensive_tier_bucket_limits_per_client():
    _reset()
    ratelimit.set_override("RL_EXPENSIVE_PER_HOUR", 3)
    # first 3 allowed, 4th blocked with a positive retry
    assert all(ratelimit.check("expensive", "ip1")["allowed"] for _ in range(3))
    blocked = ratelimit.check("expensive", "ip1")
    assert blocked["allowed"] is False
    assert blocked["retry_after"] > 0
    # a different client is unaffected (per-client keying)
    assert ratelimit.check("expensive", "ip2")["allowed"] is True


def test_cheap_tier_is_generous():
    _reset()
    ratelimit.set_override("RL_CHEAP_PER_MIN", 240)
    assert all(ratelimit.check("cheap", "ip1")["allowed"] for _ in range(100))


def test_ai_budget_degrades_to_cv_only():
    _reset()
    ratelimit.set_override("AI_BUDGET_CALLS_PER_DAY", 2)
    assert ratelimit.ai_allowed() is True
    ratelimit.record_ai_call()
    ratelimit.record_ai_call()
    assert ratelimit.ai_remaining() == 0
    assert ratelimit.ai_allowed() is False      # -> nemotron layer returns None


def test_adaptive_factor_tightens_as_budget_depletes():
    _reset()
    ratelimit.set_override("RL_EXPENSIVE_PER_HOUR", 100)
    ratelimit.set_override("AI_BUDGET_CALLS_PER_DAY", 10)
    # full budget -> factor 1.0 -> full limit
    assert ratelimit.effective_limit("expensive") == 100
    for _ in range(9):                          # remaining ratio 0.1 -> factor 0.5
        ratelimit.record_ai_call()
    assert ratelimit.effective_limit("expensive") == 50
    ratelimit.record_ai_call()                  # remaining 0 -> factor 0.25
    assert ratelimit.effective_limit("expensive") == 25


def test_concurrency_tightens_expensive_limit():
    _reset()
    ratelimit.set_override("RL_EXPENSIVE_PER_HOUR", 100)
    assert ratelimit.effective_limit("expensive") == 100
    for _ in range(4):
        ratelimit.inspection_started()          # 4 concurrent -> factor 0.5
    assert ratelimit.effective_limit("expensive") == 50


def test_snapshot_reports_live_state():
    _reset()
    ratelimit.set_override("AI_BUDGET_CALLS_PER_DAY", 5)
    ratelimit.record_ai_call()
    snap = ratelimit.snapshot()
    assert snap["ai_budget"]["used_24h"] == 1
    assert snap["ai_budget"]["remaining"] == 4
    assert "expensive" in snap["tiers"]
