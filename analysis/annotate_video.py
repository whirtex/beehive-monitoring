"""Writes a video with the detected bees and the count printed on every frame.

It is the same detector as window_counts.py (the Beehaviour YOLO11n, same
confidence), used to show the model working. Each frame carries the boxes of
the bees, the number of bees detected in it and the median of the observation
window it belongs to.

Usage (in the repository root):
    .venv/bin/python analysis/annotate_video.py video.mp4 --output detection.mp4
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE / "models" / "bee11n.pt"
YELLOW = (0, 220, 255)  # BGR, the same as the figures of the article
DARK = (35, 28, 16)
LIGHT = (233, 242, 251)


def frames_from_video(path, target_fps):
    cap = cv2.VideoCapture(str(path))
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(orig_fps / target_fps))
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield i / orig_fps, img
        i += 1
    cap.release()


def panel(img, lines):
    """Writes the lines on a dark rectangle in the top left corner."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thickness = 0.9, 2
    width = max(cv2.getTextSize(l, font, scale, thickness)[0][0] for l in lines)
    height = 20 + 40 * len(lines)
    overlay = img.copy()
    cv2.rectangle(overlay, (16, 16), (16 + width + 32, 16 + height), DARK, -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)
    for k, l in enumerate(lines):
        cv2.putText(img, l, (32, 16 + 44 + 40 * k), font, scale, LIGHT, thickness, cv2.LINE_AA)


def chart(counts, i, width, height, duration):
    """Strip with the count per frame, drawn up to frame i."""
    img = np.full((height, width, 3), DARK, np.uint8)
    left, right, top_m, bottom_m = 100, 40, 50, 50
    w, h = width - left - right, height - top_m - bottom_m
    ceiling = max(counts) + 5
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, "Bees detected per frame", (left, 34), font, 0.8, LIGHT, 2, cv2.LINE_AA)
    cv2.line(img, (left, top_m), (left, top_m + h), LIGHT, 1)
    cv2.line(img, (left, top_m + h), (left + w, top_m + h), LIGHT, 1)
    cv2.putText(img, "0", (left - 36, top_m + h + 8), font, 0.7, LIGHT, 2, cv2.LINE_AA)
    cv2.putText(img, str(ceiling), (left - 56, top_m + 8), font, 0.7, LIGHT, 2, cv2.LINE_AA)
    cv2.putText(img, "0 s", (left - 10, top_m + h + 38), font, 0.7, LIGHT, 2, cv2.LINE_AA)
    cv2.putText(img, f"{duration:g} s", (left + w - 50, top_m + h + 38), font, 0.7, LIGHT, 2, cv2.LINE_AA)
    pts = np.array([(left + int(w * k / (len(counts) - 1)), top_m + h - int(h * c / ceiling))
                    for k, c in enumerate(counts[:i + 1])], np.int32)
    if len(pts) > 1:
        cv2.polylines(img, [pts], False, YELLOW, 3, cv2.LINE_AA)
    cv2.circle(img, tuple(int(v) for v in pts[-1]), 8, YELLOW, -1, cv2.LINE_AA)
    return img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path, help="video of the hive entrance")
    p.add_argument("--output", type=Path, default=Path("detection.mp4"))
    p.add_argument("--weights", type=Path, default=WEIGHTS)
    p.add_argument("--fps", type=float, default=25, help="frames per second processed")
    p.add_argument("--window", type=float, default=5, help="seconds")
    p.add_argument("--conf", type=float, default=0.40)
    p.add_argument("--slow", type=int, default=1, help="repeat each frame N times (slow motion)")
    p.add_argument("--chart", action="store_true", help="strip with the count per frame below the video")
    a = p.parse_args()

    model = YOLO(a.weights)
    detections = []  # (t, boxes)
    for t, img in frames_from_video(a.input, a.fps):
        r = model.predict(img, conf=a.conf, imgsz=640, verbose=False)[0]
        detections.append((t, r.boxes.xyxy.cpu().numpy().astype(int)))

    medians = {}
    for k in range(int(detections[-1][0] // a.window) + 1):
        n = [len(b) for t, b in detections if k * a.window <= t < (k + 1) * a.window]
        if n:
            medians[k] = float(np.median(n))

    out_fps = (len(detections) - 1) / (detections[-1][0] - detections[0][0])
    temp = Path(tempfile.mkdtemp()) / "output.mp4"
    counts = [len(b) for _, b in detections]
    duration = round(detections[-1][0] + 1 / out_fps)
    writer = None
    for i, ((t, boxes), (_, img)) in enumerate(zip(detections, frames_from_video(a.input, a.fps))):
        for x1, y1, x2, y2 in boxes:
            cv2.rectangle(img, (x1, y1), (x2, y2), YELLOW, 2)
        k = int(t // a.window)
        start, end = k * a.window, (k + 1) * a.window
        lines = [
            f"Bees detected: {len(boxes)}",
            f"Window {start:g} to {end:g} s: median {medians[k]:g}",
        ]
        if a.slow > 1:
            lines.append(f"Slow motion: {a.slow}x")
        panel(img, lines)
        if a.chart:
            img = np.vstack([img, chart(counts, i, img.shape[1], 200, duration)])
        if writer is None:
            h, w = img.shape[:2]
            writer = cv2.VideoWriter(str(temp), cv2.VideoWriter_fourcc(*"mp4v"), out_fps, (w, h))
        for _ in range(a.slow):
            writer.write(img)
    writer.release()

    # mp4v does not play in QuickTime or in many players; H.264 plays anywhere
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(temp), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(a.output)], check=True)
    else:
        shutil.copy(temp, a.output)
    print(f"{a.output}: {len(detections)} frames at {out_fps:.1f} per second")


if __name__ == "__main__":
    main()
