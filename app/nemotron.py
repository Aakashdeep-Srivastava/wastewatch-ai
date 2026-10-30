# app/nemotron.py
# -----------------------------------------------------------------------------
# NVIDIA Nemotron on Nebius Token Factory  (the hackathon-required AI layer).
#
# Two jobs, two tiers of NVIDIA open models, served through Nebius Token
# Factory's OpenAI-compatible API:
#
#   vlm_classify()       Nemotron 3.5 Super VL  (multimodal) -> look at the
#                        ambiguous crop and name what it visually is.
#   intelligence_brief() Nemotron 3 Super / Ultra (reasoning) -> fuse the CV
#                        measurements + global environmental data into a
#                        regulator-ready brief.
#
# DESIGN CONTRACT (unchanged from the Bedrock adviser it replaces):
#   This layer is ADVISORY. It never sets a review state and never overrides the
#   deterministic policy in agent.py. CV measures, the policy decides, Nemotron
#   explains, a human confirms.
#
# CONFIG (copy the exact values from your Token Factory dashboard):
#   NEBIUS_API_KEY        required to enable this layer (absent -> graceful None)
#   NEBIUS_BASE_URL       OpenAI-compatible base, default api.studio.nebius.com/v1/
#   NEMOTRON_VL_MODEL     default nvidia/Nemotron-3.5-Super-VL
#   NEMOTRON_REASON_MODEL default nvidia/nemotron-3-super-120b-a12b
#   NEMOTRON_DEEP_MODEL   default nvidia/Nemotron-3-Ultra-550b-a55b (hard cases)
# If the key or the openai SDK is missing, every function returns None and the
# pipeline runs exactly as before. No mock data is ever substituted.
# -----------------------------------------------------------------------------
import base64
import json
import os

BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.com/v1/")
VL_MODEL = os.getenv("NEMOTRON_VL_MODEL", "nvidia/Nemotron-3.5-Super-VL")
REASON_MODEL = os.getenv("NEMOTRON_REASON_MODEL", "nvidia/nemotron-3-super-120b-a12b")
DEEP_MODEL = os.getenv("NEMOTRON_DEEP_MODEL", "nvidia/Nemotron-3-Ultra-550b-a55b")

_client = None
_tried = False


def _get_client():
    """Lazily build the Nebius OpenAI-compatible client, or None if unconfigured."""
    global _client, _tried
    if _tried:
        return _client
    _tried = True
    key = os.getenv("NEBIUS_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    try:
        _client = OpenAI(base_url=BASE_URL, api_key=key)
    except Exception:
        _client = None
    return _client


def available():
    """True when Nemotron-on-Nebius is configured and importable."""
    return _get_client() is not None


def provider_info():
    """Self-describing provenance for the UI badge and /health."""
    return {
        "provider": "Nebius Token Factory",
        "vendor": "NVIDIA",
        "available": available(),
        "models": {"vision": VL_MODEL, "reasoning": REASON_MODEL, "deep": DEEP_MODEL},
        "base_url": BASE_URL,
    }


def _extract_json(text):
    """Pull the first JSON object out of a model reply, tolerantly."""
    if not text:
        return None
    try:
        return json.loads(text[text.find("{"):text.rfind("}") + 1])
    except Exception:
        return None


def vlm_classify(crop_path):
    """Nemotron 3.5 Super VL: describe the disputed crop. Advisory only.

    Returns {visual_category, confidence, reason_short, model} or None.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        with open(crop_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return None
    prompt = (
        "You are a remote-sensing vision assistant. Classify this satellite crop "
        "as exactly one of: bare_soil, construction, possible_dumping, "
        "vegetation, water, uncertain. Describe only what is visible; do NOT "
        "decide any enforcement action. Reply with strict JSON "
        '{"visual_category": "...", "confidence": 0.0-1.0, "reason_short": "..."}.'
    )
    try:
        resp = client.chat.completions.create(
            model=VL_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}],
            max_tokens=220, temperature=0.0,
        )
        note = _extract_json(resp.choices[0].message.content)
        if note is not None:
            note["model"] = VL_MODEL
        return note
    except Exception:
        return None


def intelligence_brief(context, deep=False):
    """Nemotron reasoning model: fuse CV metrics + global environmental data
    into a regulator-ready brief. Advisory only — never a verdict.

    context: {
      location, dates, change_score, disturbed_surface, candidate_type,
      num_regions, vlm: {...}|None, enrichment: {nearest_waste_facility,
      air_quality, news}|None
    }
    Returns {headline, likely_cause, legality, severity, recommended_action,
             confidence, rationale, model} or None.
    """
    client = _get_client()
    if client is None:
        return None
    model = DEEP_MODEL if deep else REASON_MODEL
    system = (
        "You are an environmental-intelligence analyst assisting human reviewers. "
        "You are given computer-vision measurements of a satellite change plus "
        "public environmental context. Produce a concise, defensible brief. Be "
        "explicit about uncertainty. You never confirm a violation — you assess "
        "likelihood and recommend a human action. Ground every claim in the data "
        "given; if the data is insufficient, say so."
    )
    user = (
        "Analyse this detected surface change and return STRICT JSON with keys: "
        "headline (<=12 words), likely_cause (one of: illegal_dumping, "
        "landfill_expansion, construction, land_clearing, natural_or_seasonal, "
        "inconclusive), legality (one of: likely_unpermitted, likely_permitted, "
        "unknown), severity (low|medium|high), recommended_action (<=20 words), "
        "confidence (0.0-1.0), rationale (<=60 words citing the specific signals). "
        "Weigh distance to the nearest permitted waste facility heavily: a change "
        "far from any mapped/permitted site leans unpermitted; a change on top of "
        "one leans permitted expansion.\n\nDATA:\n"
        + json.dumps(context, default=str)
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_tokens=500, temperature=0.1,
        )
        brief = _extract_json(resp.choices[0].message.content)
        if brief is not None:
            brief["model"] = model
        return brief
    except Exception:
        return None
