"""Compares the YOLO11n with background subtraction, the method of Tu et al.

Background subtraction (OpenCV's MOG2) learns the image of the entrance without
bees and marks as a bee every region that differs from it. It needs no trained
model, but it needs consecutive frames to learn the background, and a bee that
stands still ends up as background. Each region counts as round(area / area of
one bee) bees, to split bees that touch, as Tu et al. do.

Both methods run on the three test videos, reduced to the width of the station
photos. The subtraction receives 10 frames per second; both are scored once per
second, only inside the entrance zone, against the hand-labelled tracks. A box
counts as a hit with IoU of 0.3, the threshold of Beehaviour: a subtraction
region does not follow the exact outline of a labelled box.

Usage (in the beehive-monitoring folder):
    .venv/bin/python analysis/background_subtraction.py --output results/background_subtraction.txt
"""

import argparse
import re
import time
from pathlib import Path

import cv2
import numpy as np

from detection import DATA, WIDTH, detect, line, load_model, metrics, shrink, video_frames

TRACKS = DATA / "tracking_and_behavior"
VIDEOS = ["20230609b-def", "20230711a-fan", "20230711b-fan"]
FPS = 10
# area of one bee in the mask (pixels, at 800 px wide), background memory (frames)
# and MOG2 threshold: the best combination of a small grid tested on the three
# videos (area 60, 100 or 150; memory 300 or 1200; threshold 16 or 25). Tuning on
# the evaluation videos favours the subtraction, not the YOLO11n
BEE_AREA = 150
MEMORY = 1200
THRESHOLD = 16


def zone(video, scale):
    text = (TRACKS / f"entrance_zone_{video}.txt").read_text()
    pts = np.array([int(v) for v in re.findall(r"\d+", text)]).reshape(-1, 2)
    return (pts * scale).astype(np.int32)


def labels(video, width, height):
    """-> {video frame (from 0): boxes x1 y1 x2 y2}. The file gives frame, track,
    left, top, width and height, normalized."""
    a = np.loadtxt(TRACKS / f"tracks_{video}.txt", delimiter=",")
    boxes = {}
    for q, _, x, y, w, h in a:
        boxes.setdefault(int(q) - 1, []).append((x * width, y * height, (x + w) * width, (y + h) * height))
    return {q: np.array(c) for q, c in boxes.items()}


def in_zone(boxes, polygon):
    if len(boxes) == 0:
        return boxes
    cx, cy = (boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2
    inside = [cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0 for x, y in zip(cx, cy)]
    return boxes[np.array(inside, bool)]


class BackgroundSubtraction:
    def __init__(self):
        self.mog = cv2.createBackgroundSubtractorMOG2(history=MEMORY, varThreshold=THRESHOLD, detectShadows=True)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def count(self, img):
        """-> boxes (one per region, repeated for each bee its area indicates)."""
        mask = self.mog.apply(img)
        mask = (mask == 255).astype(np.uint8)  # 127 is shadow
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        boxes = []
        for x, y, w, h, area in stats[1:]:
            k = round(area / BEE_AREA)
            boxes += [(x, y, x + w, y + h)] * k
        return np.array(boxes, float).reshape(-1, 4)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path)
    a = p.parse_args()

    model = load_model()
    lines = [f"YOLO11n against background subtraction, {WIDTH} px, 1 frame per second in the entrance zone, IoU >= 0.3", ""]
    everything = {"yolo": [], "bgsub": []}
    times = {"yolo": [], "bgsub": []}
    for v in VIDEOS:
        video = TRACKS / f"{v}.mp4"
        if not video.exists():
            video = DATA.parent.parent.parent / "media" / f"{v}.mp4"
        bs = BackgroundSubtraction()
        pairs = {"yolo": [], "bgsub": []}
        lab = polygon = None
        for t, img in video_frames(video, FPS):
            img = shrink(img)
            if lab is None:
                lab = labels(v, WIDTH, img.shape[0])
                polygon = zone(v, WIDTH / 1920)
            t0 = time.perf_counter()
            bg = bs.count(img)
            times["bgsub"].append(time.perf_counter() - t0)
            q = round(t * 50)
            if q % 50 or q not in lab:
                continue
            t0 = time.perf_counter()
            yolo = detect(model, img)[:, :4]
            times["yolo"].append(time.perf_counter() - t0)
            pairs["yolo"].append((in_zone(yolo, polygon), lab[q]))
            pairs["bgsub"].append((in_zone(bg, polygon), lab[q]))
        for m in pairs:
            lines.append(line(f"{v} {m:5}", metrics(pairs[m], 0.3)))
            everything[m] += pairs[m]
    lines.append("")
    for m in everything:
        lines.append(line(f"all {m:5}", metrics(everything[m], 0.3)))
        lines.append(f"  time per frame on the computer: {1000 * np.mean(times[m]):.0f} ms")

    text = "\n".join(lines)
    print(text)
    if a.output:
        a.output.write_text(text + "\n")


if __name__ == "__main__":
    main()
