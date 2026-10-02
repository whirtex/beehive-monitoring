"""Counts the visible bees in each observation window.

Input: a video of the hive entrance, or a folder of JPEG photos whose file
names are the milliseconds since the start of the window (for example
0000.jpg, 0100.jpg). The detector is the YOLO11n of the Beehaviour project,
trained on the dataset of Sledevic and Matuzevicius (see the README).

For each window, the script reports the median, the minimum and the maximum
number of bees per frame. The turnover (bees that appear in and disappear from
the image) is experimental: it has not been tuned against the ground truth and,
on the sample clip, it counts detection misses from one frame to the next as
appearances.

Usage (in the repository root):
    .venv/bin/python analysis/window_counts.py video.mp4 --fps 10 --window 5
    .venv/bin/python analysis/window_counts.py photos/2026-09-28_1430 --window 5
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE / "models" / "bee11n.pt"


def frames_from_video(path, target_fps):
    cap = cv2.VideoCapture(str(path))
    source_fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(source_fps / target_fps))
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield i / source_fps, img
        i += 1


def frames_from_folder(path):
    # each photo carries the milliseconds since the start of the window in its name
    for file in sorted(path.glob("*.jpg")):
        yield int(file.stem) / 1000, cv2.imread(str(file))


def detect(model, source, conf):
    frames = []
    for t, img in source:
        r = model.predict(img, conf=conf, imgsz=640, verbose=False)[0]
        frames.append((t, r.boxes.xyxy.cpu().numpy(), img if not frames else None))
    return frames


def centers(boxes):
    return np.column_stack(((boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2))


def turnover(frames, radius, confirm=2, tolerance=1):
    """Links the bees of neighboring frames by the distance between centers.
    A bee only counts as appeared after being seen in `confirm` frames, and as
    disappeared after being absent for more than `tolerance` frames."""
    tracks = []  # [x, y, times_seen, frames_absent, confirmed]
    events = []
    for t, boxes, _ in frames:
        pts = centers(boxes) if len(boxes) else np.zeros((0, 2))
        free = set(range(len(pts)))
        if tracks and len(pts):
            a = np.array([[tr[0], tr[1]] for tr in tracks])
            d = np.linalg.norm(a[:, None] - pts[None], axis=2)
            for r, c in zip(*linear_sum_assignment(d)):
                if d[r, c] <= radius:
                    tr = tracks[r]
                    tr[0], tr[1] = pts[c]
                    tr[2] += 1
                    tr[3] = -1
                    free.discard(c)
                    if not tr[4] and tr[2] >= confirm:
                        tr[4] = True
                        events.append((t, "appear"))
        alive = []
        for tr in tracks:
            tr[3] += 1
            if tr[3] > tolerance:
                if tr[4]:
                    events.append((t, "disappear"))
            else:
                alive.append(tr)
        tracks = alive + [[*pts[c], 1, 0, False] for c in free]
    return events


def summarize(frames, events, window):
    duration = frames[-1][0] + (frames[-1][0] - frames[-2][0])
    rows, start = [], 0.0
    while start + window <= duration + 1e-6:
        end = start + window
        n = [len(c) for t, c, _ in frames if start <= t < end]
        appear = sum(1 for t, e in events if start <= t < end and e == "appear")
        disappear = sum(1 for t, e in events if start <= t < end and e == "disappear")
        rows.append({
            "start_s": round(start, 1),
            "frames": len(n),
            "visible_median": float(np.median(n)),
            "visible_min": min(n),
            "visible_max": max(n),
            "appear": appear,
            "disappear": disappear,
            "turnover_per_min": round((appear + disappear) / 2 * 60 / window, 1),
        })
        start = end
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path, help="video or folder of photos")
    p.add_argument("--weights", type=Path, default=WEIGHTS)
    p.add_argument("--fps", type=float, default=10, help="video only")
    p.add_argument("--window", type=float, default=5, help="seconds")
    p.add_argument("--conf", type=float, default=0.40)
    p.add_argument("--csv", type=Path)
    p.add_argument("--figure", type=Path, help="first frame with the detections")
    a = p.parse_args()

    source = frames_from_folder(a.input) if a.input.is_dir() else frames_from_video(a.input, a.fps)
    frames = detect(YOLO(a.weights), source, a.conf)
    fps = (len(frames) - 1) / (frames[-1][0] - frames[0][0])
    sizes = np.concatenate([np.hypot(c[:, 2] - c[:, 0], c[:, 3] - c[:, 1]) for _, c, _ in frames if len(c)])
    # at 10 frames/s, a walking bee does not move more than its own size between two frames
    radius = np.median(sizes) * (10 / fps)
    rows = summarize(frames, turnover(frames, radius), a.window)

    print(f"{a.input}: {len(frames)} frames at {fps:.1f} per second")
    for row in rows:
        print(row)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
    if a.figure:
        _, boxes, img = frames[0]
        for x1, y1, x2, y2 in boxes.astype(int):
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 255), 2)
        cv2.imwrite(str(a.figure), img)


if __name__ == "__main__":
    main()
