"""Measures how much the ESP32 internal clock drifts, compared with the computer's.

The board runs firmware/clock_test, which wakes every 10 s and writes the time
of its own internal clock. This script records, next to each line, the time of
the computer, set over the internet. The error of the internal clock is the
difference between the time that passed for it and for the computer.

Usage (in the beehive-monitoring folder):
    .venv/bin/python analysis/clock_test.py record /dev/cu.usbserial-1120
    .venv/bin/python analysis/clock_test.py evaluate

Opening the serial port restarts the board, and the internal clock starts from
zero: the test runs from the moment record starts until Ctrl+C.
"""

import argparse
import csv
import sys
import time
from pathlib import Path

FILE = Path(__file__).parent / "data" / "clock" / "clock.csv"


def record(port):
    import serial

    FILE.parent.mkdir(parents=True, exist_ok=True)
    with serial.Serial(port, 115200, timeout=1) as s, open(FILE, "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["computer_s", "clock_s", "wakes"])
        while True:
            line = s.readline().decode(errors="replace").strip()
            now = time.time()
            if line.startswith("#"):
                print(line, flush=True)
            if not line.startswith("clock_s="):
                continue
            fields = dict(pair.split("=") for pair in line.split())
            out.writerow([f"{now:.3f}", fields["clock_s"], fields["wakes"]])
            f.flush()


def evaluate():
    with open(FILE) as f:
        rows = [(float(c), float(r), int(a)) for c, r, a in list(csv.reader(f))[1:]]
    # only the last run without a cold start (the wake counter goes back)
    resets = [i for i in range(1, len(rows)) if rows[i][2] <= rows[i - 1][2]]
    rows = rows[resets[-1] if resets else 0:]
    if len(rows) < 2:
        sys.exit("too few lines: let record run for longer")
    (c0, r0, _), (c1, r1, a1) = rows[0], rows[-1]
    hours = (c1 - c0) / 3600
    error = (r1 - r0) - (c1 - c0)
    print(f"{hours:.2f} h of test, {a1} wakes")
    print(f"the internal clock {'gained' if error > 0 else 'lost'} {abs(error):.1f} s")
    print(f"that is {abs(error) / hours:.1f} s per hour, or {abs(error) / hours * 24 / 60:.1f} min per day")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("record")
    r.add_argument("port")
    sub.add_parser("evaluate")
    a = p.parse_args()
    record(a.port) if a.action == "record" else evaluate()
