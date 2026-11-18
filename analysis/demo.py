"""Shows the detector working on a hive video, for presentations.

Each frame goes through the YOLO11n and appears with the boxes, the number of
bees and the speed of the model. Without --output, it opens a window and plays
in real time (if the computer cannot keep up, it plays slower, and the panel
shows the real speed); keys: q or Esc closes, space pauses. With --output, it
writes the annotated video, a backup in case the live one fails.

Usage (in the beehive-monitoring folder):
    .venv/bin/python analysis/demo.py media/20230711a-fan.mp4 --start 30 --duration 60
    .venv/bin/python analysis/demo.py media/20230711a-fan.mp4 --output media/detection_20230711a.mp4
"""

import argparse
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from detection import detect, load_model, shrink, video_frames

YELLOW = (0, 220, 255)  # BGR, the same as the article figures
BACKGROUND = (35, 28, 16)
LIGHT = (233, 242, 251)


def panel(img, lines):
    font = cv2.FONT_HERSHEY_SIMPLEX
    width = max(cv2.getTextSize(l, font, 0.9, 2)[0][0] for l in lines)
    cover = img.copy()
    cv2.rectangle(cover, (16, 16), (16 + width + 32, 16 + 20 + 40 * len(lines)), BACKGROUND, -1)
    cv2.addWeighted(cover, 0.75, img, 0.25, 0, img)
    for k, l in enumerate(lines):
        cv2.putText(img, l, (32, 16 + 44 + 40 * k), font, 0.9, LIGHT, 2, cv2.LINE_AA)


def annotate(model, img, t, ms):
    img = shrink(img, 1280)
    t0 = time.perf_counter()
    boxes = detect(model, img)[:, :4].astype(int)
    ms.append((time.perf_counter() - t0) * 1000)
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(img, (x1, y1), (x2, y2), YELLOW, 2)
    panel(img, ["Model: YOLO11n (Beehaviour)", f"Bees detected: {len(boxes)}",
                f"Speed: {np.mean(ms[-30:]):.0f} ms per frame", f"Video time: {t:.0f} s"])
    return img


def record(model, frames, output, fps):
    temp = Path(tempfile.mkdtemp()) / "output.mp4"
    writer, ms = None, []
    for t, img in frames:
        img = annotate(model, img, t, ms)
        if writer is None:
            writer = cv2.VideoWriter(str(temp), cv2.VideoWriter_fourcc(*"mp4v"), fps, img.shape[1::-1])
        writer.write(img)
    writer.release()
    # mp4v does not play in QuickTime or in many players; H.264 plays anywhere
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(temp), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)], check=True)
    else:
        shutil.copy(temp, output)
    print(f"{output}: {len(ms)} frames")


def live(model, frames, start):
    name = "Live bee detection"
    cv2.namedWindow(name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(name, 1280, 720)
    clock, ms = time.perf_counter(), []
    for t, img in frames:
        cv2.imshow(name, annotate(model, img, t, ms))
        # holds the frame until its time, so the video plays in real time
        key = cv2.waitKey(max(1, int((t - start - (time.perf_counter() - clock)) * 1000))) & 0xFF
        if key == ord(" "):
            pause = time.perf_counter()
            while (key := cv2.waitKey(50) & 0xFF) not in (ord(" "), ord("q"), 27):
                pass
            clock += time.perf_counter() - pause
        if key in (ord("q"), 27):
            break
    cv2.destroyAllWindows()
    if ms:
        print(f"{len(ms)} frames, model at {np.mean(ms):.0f} ms per frame")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path, help="video of the hive entrance")
    p.add_argument("--fps", type=float, default=10, help="frames per second processed")
    p.add_argument("--start", type=float, default=0, help="second where it starts")
    p.add_argument("--duration", type=float, default=0, help="seconds (0 = to the end)")
    p.add_argument("--output", type=Path, help="writes the annotated video instead of opening the window")
    a = p.parse_args()

    model = load_model()
    frames = video_frames(a.input, a.fps, a.start, a.duration)
    if a.output:
        record(model, frames, a.output, a.fps)
    else:
        live(model, frames, a.start)


if __name__ == "__main__":
    main()
