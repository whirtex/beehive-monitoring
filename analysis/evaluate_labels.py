"""Compares the YOLO11n with the hand labels of the Sledevic and Matuzevicius dataset.

Uses only the three hives that Beehaviour left out of training. Each image is
reduced to the width of the station photos before detection. The dataset does
not create the label file when the frame has no bee (its info.txt counts every
frame as labelled), so an image without a label counts as an empty frame.

The report gives, per hive and in total, the metrics of detection.metrics; the
bias by number of bees in the frame; and the error after a linear correction of
the count fitted on the other two hives (leaving one out, so as not to fit and
test on the same frames).

The detections are cached in one .npz per hive and width, so the metrics can be
recomputed without running the detector again.

Usage (in the beehive-monitoring folder):
    .venv/bin/python analysis/evaluate_labels.py --output results/label_evaluation.txt
    .venv/bin/python analysis/evaluate_labels.py --width 1280 --iou 0.3
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from detection import CONF, DATA, WIDTH, detect, line, load_model, metrics, shrink

TEST_HIVES = ["20230609b", "20230711a", "20230711b"]
# the cache keeps the detections from this confidence up; --conf filters afterwards
CACHE_CONF = 0.05
RANGES = [(0, 5), (5, 10), (10, 20), (20, 30), (30, 99)]


def read_labels(path, width, height):
    """YOLO label (class cx cy w h, normalized) -> boxes x1 y1 x2 y2 in pixels."""
    a = np.loadtxt(path, ndmin=2)
    if a.size == 0:
        return np.zeros((0, 4))
    cx, cy, w, h = a[:, 1] * width, a[:, 2] * height, a[:, 3] * width, a[:, 4] * height
    return np.column_stack((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))


def frames(hive, width, model=None):
    """-> list of (name, detections n x 5, labels m x 4), at the requested width."""
    cache = DATA / f"detections_yolo_{hive}_{width}.npz"
    if cache.exists():
        return list(np.load(cache, allow_pickle=True)["frames"])
    model = model or load_model()
    folder = DATA / "detection" / f"_bee_{hive}"
    out = []
    for path in sorted((folder / "images").glob("*.jpg")):
        img = shrink(cv2.imread(str(path)), width)
        lab = folder / "labels" / f"{path.stem}.txt"
        labels = read_labels(lab, *img.shape[1::-1]) if lab.exists() else np.zeros((0, 4))
        out.append((path.stem, detect(model, img, CACHE_CONF), labels))
    np.savez(cache, frames=np.array(out, dtype=object))
    return out


def pairs(fs, conf):
    return [(d[d[:, 4] >= conf, :4], g) for _, d, g in fs]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--width", type=int, default=WIDTH, help="image width, in pixels")
    p.add_argument("--conf", type=float, default=CONF)
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--output", type=Path, help="writes the report to this file")
    a = p.parse_args()

    lines = [f"YOLO11n against the hand labels: {a.width} px wide, confidence >= {a.conf}, IoU >= {a.iou}", ""]
    per_hive = {h: pairs(frames(h, a.width), a.conf) for h in TEST_HIVES}
    for h, ps in per_hive.items():
        lines.append(line(h, metrics(ps, a.iou)))
    everything = sum(per_hive.values(), [])
    lines.append(line("all", metrics(everything, a.iou)))

    lines += ["", "Count bias by number of labelled bees in the frame (all hives):"]
    n_det = np.array([len(d) for d, _ in everything])
    n_lab = np.array([len(g) for _, g in everything])
    for lo, hi in RANGES:
        s = (n_lab >= lo) & (n_lab < hi)
        lines.append(f"  {lo:>2} to {hi if hi < 99 else 'more':>4}: {s.sum():>4} frames, "
                     f"bias {np.mean(n_det[s] - n_lab[s]):+.1f}, error {np.mean(np.abs(n_det[s] - n_lab[s])):.1f}")

    lines += ["", "Linear correction of the count, fitted on the other two hives:"]
    for h, ps in per_hive.items():
        train = sum((v for k, v in per_hive.items() if k != h), [])
        x = np.array([len(d) for d, _ in train])
        y = np.array([len(g) for _, g in train])
        slope, icpt = np.polyfit(x, y, 1)
        det = np.array([len(d) for d, _ in ps])
        lab = np.array([len(g) for _, g in ps])
        before, after = np.mean(np.abs(det - lab)), np.mean(np.abs(slope * det + icpt - lab))
        lines.append(f"  {h}: labelled = {slope:.2f} x detected {icpt:+.2f}; error {before:.2f} -> {after:.2f}")

    text = "\n".join(lines)
    print(text)
    if a.output:
        a.output.write_text(text + "\n")


if __name__ == "__main__":
    main()
