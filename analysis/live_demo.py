"""Runs the detector live on a video, in a window, for the demonstration.

Every frame goes through the model on the spot (the Beehaviour YOLO11n, same
confidence as window_counts.py) and is shown with the boxes, the number of bees
and the speed of the model. The video plays in real time; if the computer cannot
keep up, it plays slower, and the panel shows the real speed.

Keys: q or Esc closes, space pauses.

Usage (in the repository root):
    .venv/bin/python analysis/live_demo.py media/20230711a-fan.mp4
    .venv/bin/python analysis/live_demo.py media/20230711a-fan.mp4 --start 30 --duration 60
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE / "models" / "bee11n.pt"
YELLOW = (0, 220, 255)  # BGR, the same as the figures of the article
DARK = (35, 28, 16)
LIGHT = (233, 242, 251)
WIDTH = 1280


def panel(img, lines):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thickness = 0.9, 2
    width = max(cv2.getTextSize(l, font, scale, thickness)[0][0] for l in lines)
    overlay = img.copy()
    cv2.rectangle(overlay, (16, 16), (16 + width + 32, 16 + 20 + 40 * len(lines)), DARK, -1)
    cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)
    for k, l in enumerate(lines):
        cv2.putText(img, l, (32, 16 + 44 + 40 * k), font, scale, LIGHT, thickness, cv2.LINE_AA)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path, help="video of the hive entrance")
    p.add_argument("--weights", type=Path, default=WEIGHTS)
    p.add_argument("--fps", type=float, default=25, help="frames per second processed")
    p.add_argument("--conf", type=float, default=0.40)
    p.add_argument("--start", type=float, default=0, help="second where it starts")
    p.add_argument("--duration", type=float, default=0, help="seconds to play (0 = to the end)")
    p.add_argument("--loop", action="store_true", help="go back to the start when it ends")
    p.add_argument("--max-seconds", type=float, default=0, help="closes by itself (for tests)")
    a = p.parse_args()

    model = YOLO(a.weights)
    cap = cv2.VideoCapture(str(a.input))
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(orig_fps / a.fps))
    end = a.start + a.duration if a.duration else None
    window = "Live bee detection"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, WIDTH, WIDTH * 9 // 16)

    cap.set(cv2.CAP_PROP_POS_MSEC, a.start * 1000)
    clock_start = time.perf_counter()
    frame_no, ms = 0, []
    paused = False
    while True:
        if not paused:
            ok, img = cap.read()
            if not ok or (end and cap.get(cv2.CAP_PROP_POS_MSEC) / 1000 >= end):
                if a.loop:
                    cap.set(cv2.CAP_PROP_POS_MSEC, a.start * 1000)
                    clock_start, frame_no = time.perf_counter(), 0
                    continue
                break
            frame_no += 1
            if frame_no % step:
                continue
            img = cv2.resize(img, (WIDTH, WIDTH * img.shape[0] // img.shape[1]))
            t0 = time.perf_counter()
            r = model.predict(img, conf=a.conf, imgsz=640, verbose=False)[0]
            ms.append((time.perf_counter() - t0) * 1000)
            boxes = r.boxes.xyxy.cpu().numpy().astype(int)
            for x1, y1, x2, y2 in boxes:
                cv2.rectangle(img, (x1, y1), (x2, y2), YELLOW, 2)
            video_t = frame_no / orig_fps
            panel(img, [
                "Model: YOLO11n (Beehaviour)",
                f"Bees detected: {len(boxes)}",
                f"Speed: {np.mean(ms[-30:]):.0f} ms per frame",
                f"Video time: {video_t:.0f} s",
            ])
            cv2.imshow(window, img)
            # hold the frame until its time, so the video plays in real time
            wait = frame_no / orig_fps - (time.perf_counter() - clock_start)
            key = cv2.waitKey(max(1, int(wait * 1000))) & 0xFF
        else:
            key = cv2.waitKey(50) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord(" "):
            paused = not paused
            if not paused:
                clock_start = time.perf_counter() - frame_no / orig_fps
        if a.max_seconds and time.perf_counter() - clock_start > a.max_seconds:
            break
    cap.release()
    cv2.destroyAllWindows()
    if ms:
        print(f"{len(ms)} frames, model at {np.mean(ms):.0f} ms per frame")


if __name__ == "__main__":
    main()
