# app/agent.py
# -----------------------------------------------------------------------------
# THE MANAGER of WasteWatch AI. Reads OpenCV measurements and decides the next
# action. The DETERMINISTIC rule policy is AUTHORITATIVE (reproducible, safe).
# Bedrock, if used, is an ADVISER only and can never create a review state.
#
# Loop (audit-corrected):
#   cloud_gate  -> cloudy? select_alternate_date (from a local pool)
#   coregister  -> implausible/weak? refine_ecc (residual correction)
#   detect_change (COARSE, downsampled) -> uncertain? inspect_roi_native (native)
#   decide      -> strong change -> create_review_case(PENDING_REVIEW) -> human
#   label       -> disturbed-surface regions -> "suspected dumping" (candidate)
# -----------------------------------------------------------------------------
import os
import time
import uuid

from . import vision

CLOUD_MAX = 0.20          # AOI cloud fraction above this -> alternate date
INLIER_MIN = 25           # below this (or implausible transform) -> ECC
SCORE_LOW = 0.30          # change_score in (0, LOW) -> inspect native ROI
SCORE_HIGH = 0.60         # >= HIGH -> review case
DISTURBED_MIN = 0.55      # disturbed_surface at/above this -> "suspected dumping"
COARSE_SCALE = 0.5        # first detection pass runs downsampled


def _step(trace, tool, metric, decision, emit=None):
    entry = {"step": len(trace) + 1, "tool": tool, "metric": metric,
             "decision": decision, "t": round(time.time(), 2)}
    trace.append(entry)
    if emit:
        emit(entry)
    return entry


def _label(disturbed):
    if disturbed >= DISTURBED_MIN:
        return "DISTURBED_SURFACE_CANDIDATE", "suspected dumping / landfill — pending review"
    return "CHANGE_CANDIDATE", "surface change — pending review"


def run_inspection(before_path, after_path, alt_after_paths=None, out_dir="out",
                   emit=None):
    alt = list(alt_after_paths or [])
    trace, artifacts = [], {}
    after = after_path

    # local step emitter: records to the trace AND streams live (if emit given)
    def step(tool, metric, decision):
        return _step(trace, tool, metric, decision, emit)

    # PERCEIVE: usable imagery?
    cg = vision.cloud_gate(after, out_dir); artifacts["cloud"] = cg["image"]
    if cg["cloud_ratio"] > CLOUD_MAX and alt:
        step("cloud_gate", {"cloud_ratio": cg["cloud_ratio"]},
             f"cloudy (> {CLOUD_MAX}) -> select_alternate_date")
        after = alt.pop(0)
        cg = vision.cloud_gate(after, out_dir)
        step("select_alternate_date", {"cloud_ratio": cg["cloud_ratio"]},
             "alternate observation selected")
    else:
        step("cloud_gate", {"cloud_ratio": cg["cloud_ratio"]},
             "clear enough -> proceed")

    # PERCEIVE: align (guarded homography, ECC fallback)
    co = vision.coregister(before_path, after, out_dir); artifacts["aligned"] = co["aligned"]
    if (not co.get("ok")) or co["inliers"] < INLIER_MIN:
        step("coregister",
             {"inliers": co["inliers"], "corner_disp_frac": co.get("corner_disp_frac"),
              "ok": co.get("ok")},
             f"weak/implausible (< {INLIER_MIN} inliers) -> refine_ecc")
        ecc = vision.refine_ecc(before_path, after, out_dir)
        artifacts["aligned"] = ecc["aligned"]; aligned = ecc["aligned"]
        step("refine_ecc", {"ecc": ecc["ecc"]}, "ECC residual correction applied")
    else:
        aligned = co["aligned"]
        step("coregister",
             {"inliers": co["inliers"], "inlier_ratio": co["inlier_ratio"],
              "corner_disp_frac": co["corner_disp_frac"]},
             "alignment plausible -> proceed")

    # PERCEIVE: COARSE change detection (downsampled)
    dc = vision.detect_change(before_path, aligned, out_dir, scale=COARSE_SCALE)
    artifacts["change"] = dc["image"]
    score = dc["change_score"]; disturbed = dc["mean_disturbed_surface"]

    # DECIDE: uncertain -> re-inspect the top region at NATIVE resolution
    if 0 < score < SCORE_HIGH and dc["blobs"]:
        step("detect_change",
             {"change_score": score, "num_blobs": dc["num_blobs"],
              "disturbed_surface": disturbed, "scale": COARSE_SCALE},
             f"uncertain (< {SCORE_HIGH}) -> inspect_roi_native")
        roi = vision.inspect_roi_native(before_path, aligned, dc["blobs"][0], out_dir)
        artifacts["roi"] = roi["image"]
        score = max(score, roi["roi_change_score"])
        disturbed = max(disturbed, roi["roi_disturbed_surface"])
        step("inspect_roi_native",
             {"roi_change_score": roi["roi_change_score"],
              "roi_disturbed_surface": roi["roi_disturbed_surface"]},
             "native-resolution re-analysis done")
    else:
        step("detect_change",
             {"change_score": score, "num_blobs": dc["num_blobs"],
              "disturbed_surface": disturbed}, "score outside re-inspect band")

    # ACT (deterministic; human approves any review case)
    if score >= SCORE_HIGH:
        ctype, display = _label(disturbed)
        verdict = {"status": "PENDING_REVIEW", "candidate_type": ctype,
                   "display": display, "change_score": score,
                   "disturbed_surface": disturbed, "blobs": dc["blobs"][:10]}
        step("create_review_case", {"change_score": score, "type": ctype},
             f"{display} -> PENDING_REVIEW -> authorized human approves")
    elif score <= 0.0 or dc["num_blobs"] == 0:
        verdict = {"status": "NO_SIGNIFICANT_CHANGE", "change_score": score,
                   "disturbed_surface": disturbed, "blobs": []}
        step("decide", {"change_score": score}, "no change -> log_clear")
    else:
        verdict = {"status": "NEEDS_REVIEW", "change_score": score,
                   "disturbed_surface": disturbed, "blobs": dc["blobs"][:10]}
        step("decide", {"change_score": score},
             "ambiguous -> safe default: human review")
    return verdict, trace, artifacts


# -----------------------------------------------------------------------------
# OPTIONAL Bedrock ADVISER. It classifies an ambiguous crop into a bounded
# category; it NEVER sets the review state. The deterministic policy decides.
# -----------------------------------------------------------------------------
def semantic_adviser(crop_path):
    try:
        import boto3, json, base64
    except Exception:
        return None
    try:
        client = boto3.client("bedrock-runtime",
                              region_name=os.getenv("AWS_REGION", "us-east-1"))
        with open(crop_path, "rb") as f:
            img_b = f.read()
        model = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
        prompt = ("Classify this satellite crop as one of: "
                  "bare_soil, construction, possible_dumping, vegetation, water, "
                  "uncertain. Reply JSON {\"visual_category\":...,\"confidence\":0-1,"
                  "\"reason_short\":...}. Describe only; do not decide actions.")
        resp = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [
                {"text": prompt},
                {"image": {"format": "png", "source": {"bytes": img_b}}}]}],
            inferenceConfig={"maxTokens": 200, "temperature": 0.0})
        txt = resp["output"]["message"]["content"][0]["text"]
        return json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
    except Exception:
        return None


def inspect(before_path, after_path, alt_after_paths=None, out_dir="out",
            use_adviser=False, emit=None):
    """Authoritative deterministic inspection, with an optional VLM adviser note.

    emit: optional callback(step_dict) invoked as each perceive->decide->act step
    completes, so a caller can stream the agent's reasoning live (SSE/AG-UI-style).
    """
    verdict, trace, artifacts = run_inspection(before_path, after_path,
                                               alt_after_paths, out_dir, emit=emit)
    if use_adviser and verdict["status"] in ("PENDING_REVIEW", "NEEDS_REVIEW") \
            and artifacts.get("roi") and os.getenv("ORBIT_ADVISER") == "on":
        note = semantic_adviser(artifacts["roi"])
        if note:
            verdict["adviser"] = note
            _step(trace, "semantic_adviser", note,
                  "advisory context only (non-authoritative)", emit)
    return {"id": str(uuid.uuid4())[:8], "verdict": verdict,
            "trace": trace, "artifacts": artifacts}
