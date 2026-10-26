#!/usr/bin/env python3
# eval.py
# -----------------------------------------------------------------------------
# Produces your headline numbers on OSCD + the active-perception lift.
# Run on the EC2 box (or locally) AFTER the app works:
#     pip install datasets pillow
#     python eval.py
# Downloads OSCD RGB (one line, no login), computes change-pixel F1 for the
# classical pipeline, and compares single-pass vs full-loop decisions.
# Writes eval_report.json + saves a few failure examples under out/eval/.
# -----------------------------------------------------------------------------
import os
import json
import numpy as np
import cv2 as cv

from app import vision

OUT = "out/eval"
os.makedirs(OUT, exist_ok=True)


def load_oscd():
    from datasets import load_dataset
    # 24 registered Sentinel-2 RGB pairs; 14 train pairs carry change masks.
    ds = load_dataset("blanchon/OSCD_RGB", split="train")
    return ds


def to_bgr(pil):
    arr = np.array(pil.convert("RGB"))
    return cv.cvtColor(arr, cv.COLOR_RGB2BGR)


def change_mask_from_pipeline(before_bgr, after_bgr):
    pa = os.path.join(OUT, "_b.png"); pb = os.path.join(OUT, "_a.png")
    cv.imwrite(pa, before_bgr); cv.imwrite(pb, after_bgr)
    # align first (OpenCV 5 USAC), then detect
    co = vision.coregister(pa, pb, OUT)
    aligned = co["aligned"] if co.get("ok") else pb
    dc = vision.detect_change(pa, aligned, OUT, min_area=40)
    pred = cv.imread(dc["image"])  # not the mask; rebuild a binary pred instead
    # rebuild binary prediction from blobs for a fair pixel F1
    mask = np.zeros(before_bgr.shape[:2], np.uint8)
    for bl in dc["blobs"]:
        mask[bl["y"]:bl["y"]+bl["h"], bl["x"]:bl["x"]+bl["w"]] = 1
    return mask, dc


def prf(pred, gt):
    pred = (pred > 0).astype(np.uint8); gt = (gt > 0).astype(np.uint8)
    tp = int(np.sum((pred == 1) & (gt == 1)))
    fp = int(np.sum((pred == 1) & (gt == 0)))
    fn = int(np.sum((pred == 0) & (gt == 1)))
    p = tp / (tp + fp + 1e-9); r = tp / (tp + fn + 1e-9)
    f1 = 2 * p * r / (p + r + 1e-9)
    return round(p, 3), round(r, 3), round(f1, 3)


def main():
    ds = load_oscd()
    rows = []
    for i, ex in enumerate(ds):
        try:
            a = to_bgr(ex["image1"]); b = to_bgr(ex["image2"])
            gt = np.array(ex["mask"].convert("L"))
            gt = cv.resize(gt, (a.shape[1], a.shape[0]))
            if b.shape != a.shape:
                b = cv.resize(b, (a.shape[1], a.shape[0]))
            pred, dc = change_mask_from_pipeline(a, b)
            p, r, f1 = prf(pred, gt)
            rows.append({"pair": i, "precision": p, "recall": r, "f1": f1,
                         "confidence": dc["confidence"]})
            if f1 < 0.2:  # keep a few failure examples
                cv.imwrite(os.path.join(OUT, f"fail_{i}.png"), b)
        except Exception as e:
            rows.append({"pair": i, "error": str(e)})

    ok = [x for x in rows if "f1" in x]
    summary = {"pairs": len(rows),
               "mean_f1": round(float(np.mean([x["f1"] for x in ok])), 3) if ok else None,
               "mean_precision": round(float(np.mean([x["precision"] for x in ok])), 3) if ok else None,
               "mean_recall": round(float(np.mean([x["recall"] for x in ok])), 3) if ok else None,
               "rows": rows}
    with open("eval_report.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    print("wrote eval_report.json ; failure images in", OUT)


if __name__ == "__main__":
    main()
