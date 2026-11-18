"""Results for presentations: reads the card, runs the detector and shows the chart.

Takes the last session of the card (the photos since the last start in
events.txt: the station powered on or ./simulate), runs the YOLO11n on each
photo and opens the chart of the bees counted in each photo over time, with the
median of every 30 s and, below, the temperature and humidity of
environment.csv (simulated, in a simulation). Opens the folder of the session
photos in the file browser. In the terminal, each photo with the time it
arrived, the bees, the temperature and the humidity; the figure and the CSV go
to results/presentation/.

Usage (in the beehive-monitoring folder), with the card in the computer reader:
    ./show-results                 finds the card in /Volumes
    ./show-results /Volumes/NAME   card (or folder) somewhere else
    ./show-results --all           every photo, not only the last session
    ./show-results --period 300    median of every 5 min, as in the article
"""

import argparse
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import cv2
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from detection import detect, load_model, shrink

OUTPUT = Path(__file__).resolve().parent.parent / "results" / "presentation"


def find_card():
    for v in sorted(Path("/Volumes").iterdir()) if Path("/Volumes").exists() else []:
        if (v / "events.txt").exists() or (v / "environment.csv").exists():
            return v
    raise SystemExit("Card not found in /Volumes. Put the card in the reader or pass the path.")


def session_start(card):
    """Time of the last start (station powered on, restarted or simulation)."""
    path = card / "events.txt"
    if not path.exists():
        return None, False
    start, simulation = None, False
    with open(path) as f:
        for l in f:
            date, _, text = l.strip().partition(",")
            if text.startswith("start") and date[:2] == "20":
                start, simulation = datetime.fromisoformat(date), "simulation" in text
    return start, simulation


def photos(card, since):
    for day in sorted(p for p in card.iterdir() if p.is_dir() and p.name[:2] == "20"):
        for photo in sorted(day.glob("*.jpg")):
            try:
                t = datetime.strptime(f"{day.name} {photo.stem}", "%Y-%m-%d %H%M%S")
            except ValueError:
                continue
            if since is None or t >= since:
                yield t, photo


def environment(card, since):
    """-> {date and time: (inside, outside, humidity)} from environment.csv."""
    path = card / "environment.csv"
    out = {}
    if not path.exists():
        return out
    num = lambda v: float(v) if v else np.nan  # noqa: E731
    with open(path) as f:
        for l in csv.DictReader(f):
            try:
                t = datetime.fromisoformat(f"{l['date']} {l['time']}")
            except (ValueError, KeyError):
                continue
            if since is None or t >= since:
                out[t] = (num(l.get("t_inside_c")), num(l.get("t_outside_c")), num(l.get("humidity_outside_pct")))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("card", type=Path, nargs="?")
    p.add_argument("--all", action="store_true", help="every photo, not only the last session")
    p.add_argument("--period", type=int, default=30, help="seconds of each median (default 30)")
    a = p.parse_args()
    card = a.card or find_card()
    since, simulation = (None, False) if a.all else session_start(card)

    found = list(photos(card, since))
    if not found:
        raise SystemExit(f"No photo in {card}" + (f" since {since}" if since else ""))
    print(f"Card: {card}")
    print(f"{len(found)} photos, from {found[0][0]:%H:%M:%S} to {found[-1][0]:%H:%M:%S}")
    # opens the folder of the session photos while the detector runs
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    for folder in sorted({str(f.parent) for _, f in found}):
        subprocess.run([opener, folder])

    model = load_model()
    times, counts = [], []
    for i, (t, photo) in enumerate(found, 1):
        img = cv2.imread(str(photo))
        if img is None:
            continue
        times.append(t)
        counts.append(len(detect(model, shrink(img))))
        print(f"\r  detector: {i}/{len(found)} photos", end="", flush=True)
    print()
    counts = np.array(counts)

    periods = {}
    for t, n in zip(times, counts):
        periods.setdefault(datetime.fromtimestamp(t.timestamp() // a.period * a.period), []).append(n)

    env = environment(card, since)
    kind = "simulated" if simulation else "measured"
    print(f"\nEach photo (temperature and humidity {kind}):")
    for t, n in zip(times, counts):
        e = env.get(t)
        extra = f"   inside {e[0]:.2f} C   outside {e[1]:.1f} C   {e[2]:.0f} %" if e else ""
        print(f"  {t:%H:%M:%S}  {n:3d} bees{extra}")

    print(f"\nBees per photo: mean {counts.mean():.1f}, minimum {counts.min()}, maximum {counts.max()}")
    print(f"Median of every {a.period} s:")
    for start, ns in sorted(periods.items()):
        print(f"  {start:%H:%M:%S}  {np.median(ns):5.1f} bees  ({len(ns)} photos)")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = f"{times[0]:%Y-%m-%d_%H%M}"
    with open(OUTPUT / f"count_{stamp}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date_time", "bees"])
        w.writerows([(f"{t:%Y-%m-%d %H:%M:%S}", n) for t, n in zip(times, counts)])

    if env:
        fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 8.5), sharex=True, height_ratios=[2, 1])
    else:
        fig, ax = plt.subplots(figsize=(13, 6.5))
    ax.plot(times, counts, "o", color="#e0a400", ms=7, label="bees in each photo", zorder=3)
    starts = sorted(periods)
    # each median at the mean instant of the photos of its period
    middle = [datetime.fromtimestamp(np.mean([t.timestamp() for t in times
                                              if s.timestamp() <= t.timestamp() < s.timestamp() + a.period]))
              for s in starts]
    ax.plot(middle, [np.median(periods[s]) for s in starts], "-", color="#7a4a00", lw=3,
            label=f"median of every {a.period} s", zorder=2)
    title = "Bees at the entrance" + (" (simulation with a video)" if simulation else "")
    fig.suptitle(f"{title}: {len(times)} photos, from {times[0]:%H:%M} to {times[-1]:%H:%M}",
                 fontsize=17, fontweight="bold")
    ax.set_title("Counted by the detector (YOLO11n), one photo every 10 s", fontsize=13)
    ax.set_ylabel("bees", fontsize=13)
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.25)
    ax.legend(loc="lower right", frameon=False, fontsize=12)
    short = (times[-1] - times[0]).total_seconds() < 600
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S" if short else "%H:%M"))
    if env:
        te = sorted(env)
        ax2.plot(te, [env[t][0] for t in te], "o-", color="#c0392b", lw=2, ms=4, label="inside")
        ax2.plot(te, [env[t][1] for t in te], "s-", color="#2e86c1", lw=2, ms=4, label="outside")
        ax2.set_ylabel("°C", fontsize=12)
        ax3 = ax2.twinx()
        ax3.plot(te, [env[t][2] for t in te], "^--", color="#7f8c8d", lw=1.5, ms=4, label="humidity outside")
        ax3.set_ylabel("humidity (%)", fontsize=12)
        h1, l1 = ax2.get_legend_handles_labels()
        h3, l3 = ax3.get_legend_handles_labels()
        ax2.legend(h1 + h3, l1 + l3, loc="center right", frameon=False, fontsize=11)
        ax2.set_title(f"Temperature and humidity ({kind})", fontsize=13)
        ax2.grid(alpha=0.25)
    fig.savefig(OUTPUT / f"results_{stamp}.png", dpi=110, bbox_inches="tight")
    print(f"\nFigure and CSV in {OUTPUT}")
    plt.show()


if __name__ == "__main__":
    main()
