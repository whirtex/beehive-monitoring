"""Measures how much the window length changes the count of visible bees.

Runs the detector on a video of the entrance, at the resolution and rate of the
station (1280 x 720, 10 frames per second), and compares the median number of
bees per frame of each short window with the median of the whole minute it
falls in. The reference is the minute because the interval schedule was
validated with 1-minute windows (sampling_intervals.py).

Usage (in the repository root):
    .venv/bin/python analysis/window_length.py video.mp4
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

FOLDER = Path(__file__).resolve().parent
WEIGHTS = FOLDER / "models" / "bee11n.pt"


def count(model, path, target_fps, conf):
    cap = cv2.VideoCapture(str(path))
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(orig_fps / target_fps))
    times, counts, i = [], [], 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if i % step == 0:
            img = cv2.resize(img, (1280, 720))
            r = model.predict(img, conf=conf, imgsz=640, verbose=False)[0]
            times.append(i / orig_fps)
            counts.append(len(r.boxes))
        i += 1
    return np.array(times), np.array(counts)


def median(times, counts, start, end):
    return float(np.median(counts[(times >= start) & (times < end)]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video", type=Path)
    p.add_argument("--weights", type=Path, default=WEIGHTS)
    p.add_argument("--fps", type=float, default=10)
    p.add_argument("--conf", type=float, default=0.40)
    p.add_argument("--windows", type=int, nargs="+", default=[5, 10, 30], help="seconds")
    a = p.parse_args()

    times, counts = count(YOLO(a.weights), a.video, a.fps, a.conf)
    minutes = int((times[-1] + 1 / a.fps) // 60)
    print(f"{a.video}: {len(counts)} frames, {minutes} min, from {counts.min()} to {counts.max()} bees per frame")
    for m in range(minutes):
        print(f"minute {m + 1}: median of {median(times, counts, 60 * m, 60 * m + 60):.1f} bees")
    for w in a.windows:
        diff, rel = [], []
        for m in range(minutes):
            ref = median(times, counts, 60 * m, 60 * m + 60)
            for start in range(60 * m, 60 * m + 60, w):
                d = abs(median(times, counts, start, start + w) - ref)
                diff.append(d)
                rel.append(d / ref)
        print(f"{w:>2} s window: median difference of {np.median(diff):.1f} bees ({100 * np.median(rel):.0f}%), "
              f"worst case of {max(diff):.1f} ({100 * max(rel):.0f}%), over {len(diff)} windows")


if __name__ == "__main__":
    main()
