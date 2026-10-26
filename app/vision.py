# app/vision.py
# -----------------------------------------------------------------------------
# THE EYES of WasteWatch AI. Each function only looks and measures (no decisions).
# OpenCV 5 throughout. Honest about what it does: it measures scene quality,
# residual alignment, change, and a DISTURBED-SURFACE heuristic (NOT "waste").
#
# Key corrections vs the first draft (audit P0/P1):
#  - detect_change runs the COARSE pass downsampled; inspect_roi_native re-reads
#    the candidate at ORIGINAL resolution -> genuine higher-fidelity re-analysis,
#    not bicubic upscaling of the same pixels.
#  - CLAHE is used for ORB/preview only, NOT inside the temporal difference.
#    The difference uses a light cross-date mean normalization instead.
#  - coregister sanity-checks the transform (corner displacement) and reports
#    residual metrics; the agent falls back to ECC when it looks implausible.
#  - "disturbed_surface_score", not "waste". No sub-pixel / default-USAC claims.
# -----------------------------------------------------------------------------
import os
import time
import cv2 as cv
import numpy as np

DNN_ENGINE = getattr(cv.dnn, "ENGINE_NEW", getattr(cv.dnn, "ENGINE_OPENCV", None))


def _imread(path):
    img = cv.imread(path, cv.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"could not read image: {path}")
    return img


def _save(img, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, name)
    cv.imwrite(p, img)
    return p


# -----------------------------------------------------------------------------
# cloud_gate: usable-image check. HONEST LIMIT: on RGB-only tiles this is a
# brightness/low-saturation heuristic. With Sentinel-2 L2A, the Scene
# Classification (SCL) cloud/shadow mask is the correct source (roadmap).
# -----------------------------------------------------------------------------
def cloud_gate(image_path, out_dir="out"):
    t = time.time()
    img = _imread(image_path)
    hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
    mask = cv.inRange(hsv, (0, 0, 180), (180, 40, 255))
    cloud_ratio = float(np.count_nonzero(mask)) / mask.size
    overlay = img.copy()
    overlay[mask > 0] = (0, 0, 255)
    vis = cv.addWeighted(img, 0.7, overlay, 0.3, 0)
    path = _save(vis, out_dir, "cloud_mask.png")
    return {"tool": "cloud_gate", "cloud_ratio": round(cloud_ratio, 4),
            "method": "rgb_heuristic", "image": path,
            "ms": int((time.time() - t) * 1000)}


# -----------------------------------------------------------------------------
# coregister: ORB -> BFMatcher -> findHomography(USAC_MAGSAC) -> warpPerspective.
# Reports inliers AND a transform sanity check (corner displacement). CLAHE is
# applied ONLY to the grayscale used for feature detection.
# -----------------------------------------------------------------------------
def coregister(before_path, after_path, out_dir="out", max_corner_frac=0.15):
    t = time.time()
    img1 = _imread(before_path)
    img2 = _imread(after_path)
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1 = clahe.apply(cv.cvtColor(img1, cv.COLOR_BGR2GRAY))
    g2 = clahe.apply(cv.cvtColor(img2, cv.COLOR_BGR2GRAY))

    orb = cv.ORB_create(nfeatures=4000)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)

    res = {"tool": "coregister", "method": "USAC_MAGSAC"}
    if d1 is None or d2 is None or len(k1) < 10 or len(k2) < 10:
        res.update(ok=False, reason="too few features", inliers=0,
                   inlier_ratio=0.0, corner_disp_frac=1.0,
                   aligned=after_path, ms=int((time.time()-t)*1000))
        return res

    bf = cv.BFMatcher(cv.NORM_HAMMING, crossCheck=True)
    matches = sorted(bf.match(d1, d2), key=lambda m: m.distance)[:500]
    if len(matches) < 12:
        res.update(ok=False, reason="too few matches", inliers=0,
                   inlier_ratio=0.0, corner_disp_frac=1.0,
                   aligned=after_path, ms=int((time.time()-t)*1000))
        return res

    pts1 = np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    pts2 = np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, inlier_mask = cv.findHomography(pts2, pts1, cv.USAC_MAGSAC, 3.0)
    if H is None:
        res.update(ok=False, reason="homography failed", inliers=0,
                   inlier_ratio=0.0, corner_disp_frac=1.0,
                   aligned=after_path, ms=int((time.time()-t)*1000))
        return res

    h, w = img1.shape[:2]
    # transform sanity: how far does the warp move the image corners?
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    warped_c = cv.perspectiveTransform(corners, H).reshape(-1, 2)
    disp = np.linalg.norm(warped_c - corners.reshape(-1, 2), axis=1).max()
    corner_disp_frac = float(disp / np.hypot(w, h))

    inliers = int(inlier_mask.sum())
    aligned = cv.warpPerspective(img2, H, (w, h))
    aligned_path = _save(aligned, out_dir, "aligned.png")
    plausible = corner_disp_frac <= max_corner_frac
    res.update(ok=plausible, inliers=inliers,
               inlier_ratio=round(inliers / max(len(matches), 1), 3),
               matches=len(matches),
               corner_disp_frac=round(corner_disp_frac, 3),
               reason=("ok" if plausible else "implausible transform"),
               aligned=aligned_path, ms=int((time.time()-t)*1000))
    return res


def refine_ecc(before_path, after_path, out_dir="out"):
    """Constrained (affine) residual alignment + fallback. OpenCV 5 ECC."""
    t = time.time()
    img1 = _imread(before_path)
    img2 = _imread(after_path)
    g1 = cv.cvtColor(img1, cv.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    g2 = cv.cvtColor(img2, cv.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    warp = np.eye(2, 3, dtype=np.float32)
    crit = (cv.TERM_CRITERIA_EPS | cv.TERM_CRITERIA_COUNT, 200, 1e-5)
    try:
        cc, warp = cv.findTransformECC(g1, g2, warp, cv.MOTION_AFFINE, crit, None, 5)
    except cv.error:
        cc = -1.0
    h, w = img1.shape[:2]
    aligned = cv.warpAffine(img2, warp, (w, h),
                            flags=cv.INTER_LINEAR + cv.WARP_INVERSE_MAP)
    return {"tool": "refine_ecc", "ecc": round(float(cc), 3),
            "aligned": _save(aligned, out_dir, "aligned_ecc.png"),
            "ms": int((time.time() - t) * 1000)}


# -----------------------------------------------------------------------------
# disturbed_surface_score: HONEST heuristic for exposed/disturbed ground.
# High when bright + low-saturation + non-vegetated + textured. This is NOT a
# waste detector; the same signature fits quarries, construction, bare soil.
# -----------------------------------------------------------------------------
def disturbed_surface_score(bgr):
    if bgr.size == 0:
        return 0.0
    hsv = cv.cvtColor(bgr, cv.COLOR_BGR2HSV)
    val = float(hsv[:, :, 2].mean()) / 255.0
    sat = float(hsv[:, :, 1].mean()) / 255.0
    b, g, r = cv.split(bgr.astype(np.float32))
    greenness = float((g - (r + b) / 2.0).mean()) / 255.0          # veg is high
    nonveg = 1.0 - float(np.clip(greenness / 0.08, 0, 1))
    tex = cv.Laplacian(cv.cvtColor(bgr, cv.COLOR_BGR2GRAY), cv.CV_64F).var()
    tex_term = float(np.clip(tex / 500.0, 0, 1))
    score = 0.35 * val + 0.30 * (1 - sat) + 0.25 * nonveg + 0.10 * tex_term
    return round(float(np.clip(score, 0, 1)), 3)


def _norm_lab(img):
    """Lab, with a light cross-date mean shift. No CLAHE in the diff path."""
    return cv.cvtColor(img, cv.COLOR_BGR2Lab).astype(np.int16)


# -----------------------------------------------------------------------------
# detect_change: coarse pass is downsampled (scale<1) so a later native-res
# re-inspection genuinely adds detail. Difference is CLAHE-free; per-region
# disturbed_surface_score attached. Returns blobs in FULL-RES coordinates.
# -----------------------------------------------------------------------------
def detect_change(before_path, after_path, out_dir="out", min_area=120, scale=1.0):
    t = time.time()
    a_full = _imread(before_path)
    b_full = _imread(after_path)
    if a_full.shape != b_full.shape:
        b_full = cv.resize(b_full, (a_full.shape[1], a_full.shape[0]))

    if scale != 1.0:
        a = cv.resize(a_full, None, fx=scale, fy=scale, interpolation=cv.INTER_AREA)
        b = cv.resize(b_full, None, fx=scale, fy=scale, interpolation=cv.INTER_AREA)
    else:
        a, b = a_full, b_full

    la, lb = _norm_lab(a), _norm_lab(b)
    lb = lb + (la.reshape(-1, 3).mean(0) - lb.reshape(-1, 3).mean(0)).astype(np.int16)
    diff = cv.absdiff(la, lb).astype(np.uint8)
    gray = cv.cvtColor(cv.cvtColor(diff, cv.COLOR_Lab2BGR), cv.COLOR_BGR2GRAY)
    gray = cv.GaussianBlur(gray, (5, 5), 0)

    _, th = cv.threshold(gray, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    k = cv.getStructuringElement(cv.MORPH_ELLIPSE, (5, 5))
    th = cv.morphologyEx(th, cv.MORPH_OPEN, k, 1)
    th = cv.morphologyEx(th, cv.MORPH_CLOSE, k, 2)

    n, _, stats, _ = cv.connectedComponentsWithStats(th, connectivity=8)
    inv = 1.0 / scale
    blobs, total_area, vis = [], 0, b_full.copy()
    eff_min = min_area * (scale ** 2)
    for i in range(1, n):
        area = int(stats[i, cv.CC_STAT_AREA])
        if area < eff_min:
            continue
        x = int(stats[i, cv.CC_STAT_LEFT] * inv); y = int(stats[i, cv.CC_STAT_TOP] * inv)
        w = int(stats[i, cv.CC_STAT_WIDTH] * inv); h = int(stats[i, cv.CC_STAT_HEIGHT] * inv)
        crop = b_full[y:y+h, x:x+w]
        ds = disturbed_surface_score(crop)
        area_full = int(area * inv * inv)
        blobs.append({"x": x, "y": y, "w": w, "h": h, "area": area_full,
                      "disturbed_surface": ds})
        total_area += area_full
        cv.rectangle(vis, (x, y), (x+w, y+h), (0, 0, 255), 2)

    full_px = a_full.shape[0] * a_full.shape[1]
    changed_ratio = total_area / full_px
    biggest = max((bl["area"] for bl in blobs), default=0)
    mean_ds = round(float(np.mean([bl["disturbed_surface"] for bl in blobs])), 3) if blobs else 0.0
    # transparent composite score (documented in the report), not a probability
    change_score = round(min(1.0, (changed_ratio * 8) + (biggest / full_px) * 6), 3)

    return {"tool": "detect_change", "scale": scale,
            "num_blobs": len(blobs), "changed_ratio": round(float(changed_ratio), 4),
            "change_score": change_score, "mean_disturbed_surface": mean_ds,
            "blobs": sorted(blobs, key=lambda z: -z["area"])[:20],
            "image": _save(vis, out_dir, "change_map.png"),
            "ms": int((time.time() - t) * 1000)}


# -----------------------------------------------------------------------------
# inspect_roi_native: active perception done honestly. Crop the candidate from
# the ORIGINAL full-res images and re-detect at native resolution. Because the
# first pass ran downsampled, this really does expose more spatial information.
# -----------------------------------------------------------------------------
def inspect_roi_native(before_path, after_path, box, out_dir="out", pad=8):
    t = time.time()
    a = _imread(before_path); b = _imread(after_path)
    if a.shape != b.shape:
        b = cv.resize(b, (a.shape[1], a.shape[0]))
    H, W = a.shape[:2]
    x = max(0, box["x"] - pad); y = max(0, box["y"] - pad)
    x2 = min(W, box["x"] + box["w"] + pad); y2 = min(H, box["y"] + box["h"] + pad)
    pa = _save(a[y:y2, x:x2], out_dir, "roi_before.png")
    pb = _save(b[y:y2, x:x2], out_dir, "roi_after.png")
    sub = detect_change(pa, pb, out_dir=out_dir, min_area=40, scale=1.0)  # native
    return {"tool": "inspect_roi_native", "box": box,
            "roi_change_score": sub["change_score"],
            "roi_disturbed_surface": sub["mean_disturbed_surface"],
            "roi_blobs": sub["num_blobs"], "image": sub["image"],
            "ms": int((time.time() - t) * 1000)}


if __name__ == "__main__":
    os.makedirs("out", exist_ok=True)
    rng = np.random.default_rng(1)
    base = rng.integers(60, 180, (256, 256, 3), dtype=np.uint8)
    after = base.copy()
    cv.rectangle(after, (150, 150), (205, 205), (210, 210, 215), -1)  # bright bare patch
    cv.imwrite("out/_a.png", base); cv.imwrite("out/_b.png", after)
    print("cloud :", cloud_gate("out/_a.png"))
    print("coreg :", coregister("out/_a.png", "out/_b.png"))
    print("change:", detect_change("out/_a.png", "out/_b.png", scale=0.5))
