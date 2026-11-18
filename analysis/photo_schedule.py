"""Chooses how to spread the photos over time, with the hand-labelled tracks.

For the three test videos (2 min at 50 frames per second each), the Sledevic and
Matuzevicius dataset gives the box of every bee in every consecutive frame,
inside the entrance zone. The number of boxes per frame is the true count, with
no detector in between.

The questions:
1. Does the frame rate inside a window change the window median? Compares the
   median of each 10 s window taken at 10, 5, 2 and 1 frame per second with the
   median of the same window at 50.
2. Which schedule best estimates the occupancy of the entrance? Compares bursts
   (consecutive windows) with single photos spread over time, all against the
   median of the whole 2 min, testing every possible start.
3. Does the answer to 2 hold for the 5 min period of the station? The frames of
   the detection dataset of hive 20230711a are one every 30 of a continuous
   recording of about 13 min, all labelled by hand. Compares the 10 s burst (the
   old schedule, one per period) with single photos against the median of each
   5 min period, sliding the period second by second. The dataset does not give
   the rate of this recording; it assumes 50 frames per second, like the track
   videos of the same hive and day (at 30, the recording would last 22 min and
   the result is the same).
4. And on a video of hours, without labels? The video "Two hour - Beehive
   entrance cam!" (Bee Cast, YouTube, CC BY) films a hive entrance for 2 h with a
   fixed camera. The detector counts the bees on the landing board twice per
   second, and the comparison of 3 runs on this count. The detector misses some
   bees and counts a few screws, but always in the same way, so the error enters
   every schedule equally (in 3, the comparison with the detector count gave the
   same order as with the labels). The count is cached in analysis/data/youtube/;
   to redo it, download the video to media/:
       yt-dlp -f 136 -o "media/%(id)s.%(ext)s" "https://www.youtube.com/watch?v=9NnmqDTvSuw"
   (if YouTube asks for a login, add --cookies-from-browser <browser>).

It also reports the share of the bees in each behaviour labelled in the dataset.

Usage (in the beehive-monitoring folder):
    .venv/bin/python analysis/photo_schedule.py --output results/photo_schedule.txt
"""

import argparse
from pathlib import Path

import numpy as np

from detection import DATA, FOLDER, load_model, video_frames

TRACKS = DATA / "tracking_and_behavior"
VIDEOS = ["20230609b-def", "20230711a-fan", "20230711b-fan"]
FPS = 50
# behaviour columns after the box. The dataset has no legend; the order was
# checked by the motion: the bees of the third column move 0.4 to 0.7 px per frame
# (still, fanning), those of the first 2.4 px (passing), and the second only
# appears in the defence video
BEHAVIOURS = ["foraging", "defence", "fanning", "washboarding"]
# (name, burst length in s, photos per second); length 0 = single photos
SCHEDULES = [
    ("10 s burst at 10/s (100 photos)", 10, 10),
    ("10 s burst at 1/s (10 photos)", 10, 1),
    ("30 s burst at 1/s (30 photos)", 30, 1),
    ("1 photo every 5 s (24 photos)", 0, 1 / 5),
    ("1 photo every 10 s (12 photos)", 0, 1 / 10),
    ("1 photo every 20 s (6 photos)", 0, 1 / 20),
]
PERIOD_SCHEDULES = [("10 s burst, one per period", 0), ("1 photo every 5 s (60 photos)", 5),
                    ("1 photo every 10 s (30 photos)", 10), ("1 photo every 20 s (15 photos)", 20),
                    ("1 photo every 60 s (5 photos)", 60)]


def read(video):
    """-> (count per frame, track table with behaviour)."""
    a = np.loadtxt(TRACKS / f"tracks_and_behavior_classes_{video}.txt", delimiter=",")
    return np.bincount(a[:, 0].astype(int) - 1), a


def schedule_errors(c, length, per_s):
    """Absolute error of the sample median against the video median, for each start."""
    ref = np.median(c)
    step = round(FPS / per_s)
    if length:
        n = length * FPS
        return [abs(np.median(c[i:i + n:step]) - ref) for i in range(0, len(c) - n + 1, FPS)]
    return [abs(np.median(c[i::step]) - ref) for i in range(0, step, FPS // 5)]


def long_count(hive="20230711a"):
    """-> (instant in s, labelled bees) of the frames of the detection dataset.

    The dataset does not create the label file of a frame without bees."""
    folder = DATA / "detection" / f"_bee_{hive}"
    frames = sorted(int(a.stem[len(hive):]) for a in (folder / "images").glob("*.jpg"))
    def n(q):
        lab = folder / "labels" / f"{hive}{q}.txt"
        return sum(1 for l in open(lab) if l.strip()) if lab.exists() else 0
    return (np.array(frames) - frames[0]) / FPS, np.array([n(q) for q in frames])


def period_errors(t, c, spacing, period=300):
    """Error against the median of each 5 min period. spacing 0 = 10 s bursts."""
    errors = []
    for s in np.arange(0, t[-1] - period, 1.0):
        ref = np.median(c[(t >= s) & (t < s + period)])
        if spacing:
            for o in np.arange(0, spacing, 1.0):
                i = np.minimum(np.searchsorted(t, s + np.arange(o, period, spacing)), len(t) - 1)
                errors.append(abs(np.median(c[i]) - ref))
        else:
            errors += [abs(np.median(c[(t >= b) & (t < b + 10)]) - ref) for b in np.arange(s, s + period - 9, 10)]
    return errors


YOUTUBE = "9NnmqDTvSuw"
# landing board in the 1280 x 720 video: rows and columns
BOARD = (280, 580, 90, 1270)


def youtube_count():
    """-> (instant in s, bees on the board), twice per second, cached."""
    cache = DATA.parent / "youtube" / f"count_{YOUTUBE}.npz"
    if cache.exists():
        d = np.load(cache)
        return d["t"], d["n"]
    import torch
    from torchvision.ops import nms
    model = load_model()
    y0, y1, x0, x1 = BOARD
    ts, ns = [], []
    for t, img in video_frames(FOLDER.parent / "media" / f"{YOUTUBE}.mp4", 2):
        # two overlapping halves, at the original size: the bees keep the size the
        # detector saw in training
        board, boxes = img[y0:y1, x0:x1], []
        w = board.shape[1]
        for a, b in [(0, w // 2 + w // 8), (w // 2 - w // 8, w)]:
            r = model.predict(board[:, a:b], conf=0.25, imgsz=640, verbose=False)[0]
            xy = r.boxes.xyxy.cpu().numpy()
            xy[:, [0, 2]] += a
            boxes += [np.append(c, s) for c, s in zip(xy, r.boxes.conf.cpu().numpy())]
        c = torch.tensor(np.array(boxes).reshape(-1, 5), dtype=torch.float32)
        ts.append(t)
        ns.append(len(nms(c[:, :4], c[:, 4], 0.4)))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, t=np.array(ts), n=np.array(ns))
    return np.array(ts), np.array(ns)


def rate_errors(c, per_s, length=10):
    n, step = length * FPS, round(FPS / per_s)
    return [abs(np.median(c[i:i + n:step]) - np.median(c[i:i + n])) for i in range(0, len(c) - n + 1, FPS)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path)
    a = p.parse_args()

    counts = {}
    lines = ["True count (hand-labelled tracks), entrance zone, 2 min at 50 frames/s", ""]
    for v in VIDEOS:
        c, tab = read(v)
        counts[v] = c
        lines.append(f"{v}: median of {np.median(c):.0f} bees per frame (from {c.min()} to {c.max()}); "
                     + ", ".join(f"{n} {100 * x:.0f}%" for n, x in zip(BEHAVIOURS, tab[:, 6:10].mean(axis=0))))

    lines += ["", "1. Median of a 10 s window taken at fewer frames per second, against the same at 50/s",
              "   (difference in bees: median and 90th percentile, over the three videos)"]
    for f in [10, 5, 2, 1]:
        e = sum((rate_errors(c, f) for c in counts.values()), [])
        lines.append(f"   {f:>2} per second: {np.median(e):.1f} ({np.percentile(e, 90):.1f})")

    lines += ["", "2. Error of the schedule against the median of the 2 min (bees: median and 90th percentile)",
              f"   {'':36}" + "".join(f"{v:>16}" for v in VIDEOS)]
    for name, length, per_s in SCHEDULES:
        cells = [schedule_errors(counts[v], length, per_s) for v in VIDEOS]
        lines.append(f"   {name:36}" + "".join(f"{np.median(e):>9.1f} ({np.percentile(e, 90):4.1f})" for e in cells))

    t, c = long_count()
    medians = [np.median(c[(t >= s) & (t < s + 300)]) for s in np.arange(0, t[-1] - 300, 10)]
    lines += ["", f"3. Error against the median of each 5 min period, {t[-1] / 60:.0f} min recording of 20230711a",
              f"   ({len(t)} labelled frames, one every {t[1]:.1f} s; median {np.median(c):.0f} bees, from {c.min()} to {c.max()};",
              f"   the 5 min median goes from {min(medians):.0f} to {max(medians):.0f} over the recording)"]
    for name, spacing in PERIOD_SCHEDULES:
        e = period_errors(t, c, spacing)
        lines.append(f"   {name:36}{np.median(e):>9.1f} ({np.percentile(e, 90):4.1f})")

    t, c = youtube_count()
    medians = [np.median(c[(t >= s) & (t < s + 300)]) for s in np.arange(0, t[-1] - 300, 60)]
    lines += ["", f"4. The same, on the {t[-1] / 60:.0f} min YouTube video ({YOUTUBE}), with the detector count on the board",
              f"   (two frames per second; the 5 min median goes from {min(medians):.0f} to {max(medians):.0f} over the video)"]
    for name, spacing in PERIOD_SCHEDULES:
        e = period_errors(t, c, spacing)
        lines.append(f"   {name:36}{np.median(e):>9.1f} ({np.percentile(e, 90):4.1f})")

    text = "\n".join(lines)
    print(text)
    if a.output:
        a.output.write_text(text + "\n")


if __name__ == "__main__":
    main()
