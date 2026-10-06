"""Measures how much is lost by observing the entrance in intervals instead of nonstop.

Input: the flow files of the Beehive Metrics dataset (Kaggle, HOBOS project),
with arrivals and departures counted at the entrance every minute, at two German
hives. The dataset does not declare a license, so the files are not in the
repository: download them to analysis/data/hobos/.

    curl -L -o flow_schwartau.zip \
        https://www.kaggle.com/api/v1/datasets/download/se18m502/bee-hive-metrics/flow_schwartau.csv

The activity of a minute is the sum of arrivals and departures. For each
interval, the script simulates a station that observes a 1-minute window every
N minutes and multiplies what it saw by N. All N possible offsets are tested,
because no start time is more correct than another. The dataset has no
resolution below 1 minute, so 5 s windows cannot be simulated here.

Usage (in the repository root):
    .venv/bin/python analysis/sampling_intervals.py analysis/data/hobos/flow_*.csv
"""

import argparse
import csv
import datetime as dt
from collections import defaultdict
from pathlib import Path

import numpy as np

MONTHS = (5, 6, 7, 8, 9)  # flight season in Germany


def activity_per_minute(path):
    # arrivals (positive) and departures (negative) come in rows with the same time
    act = defaultdict(float)
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for t, v in r:
            act[t] += abs(float(v))
    # the dataset has impossible minutes, such as 8 thousand bees; clip at the 99.99th percentile
    cap = np.percentile(list(act.values()), 99.99)
    days = defaultdict(lambda: np.full(1440, np.nan))
    for t, v in act.items():
        x = dt.datetime.fromisoformat(t)
        days[x.date()][x.hour * 60 + x.minute] = min(v, cap)
    return days, cap


def valid_days(days, minimum):
    """Complete days of the flight season, without the days with almost no flight (rain)."""
    for d, m in sorted(days.items()):
        if d.month in MONTHS and not np.isnan(m).any() and m.sum() >= minimum:
            yield d, m


def compare(days, interval, min_hour):
    day_error, hour_error, right_peak = [], [], []
    for _, m in days:
        hours = m.reshape(24, 60).sum(axis=1)
        for offset in range(interval):
            sample = np.zeros(1440)
            sample[offset::interval] = m[offset::interval] * interval
            hours_s = sample.reshape(24, 60).sum(axis=1)
            day_error.append(abs(sample.sum() - m.sum()) / m.sum())
            ok = hours >= min_hour
            hour_error.extend(np.abs(hours_s[ok] - hours[ok]) / hours[ok])
            right_peak.append(hours_s.argmax() == hours.argmax())
    return {
        "interval_min": interval,
        "day_error_median_%": round(100 * float(np.median(day_error)), 1),
        "day_error_p95_%": round(100 * float(np.percentile(day_error, 95)), 1),
        "hour_error_median_%": round(100 * float(np.median(hour_error)), 1),
        "hour_error_p95_%": round(100 * float(np.percentile(hour_error, 95)), 1),
        "peak_at_right_hour_%": round(100 * float(np.mean(right_peak)), 1),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("files", type=Path, nargs="+", help="flow_<hive>.csv")
    p.add_argument("--intervals", type=int, nargs="+", default=[2, 5, 10, 15, 30])
    p.add_argument("--day-minimum", type=float, default=100, help="crossings in the day")
    p.add_argument("--hour-minimum", type=float, default=500, help="crossings in the hour")
    p.add_argument("--csv", type=Path)
    a = p.parse_args()

    rows = []
    for f in a.files:
        days, cap = activity_per_minute(f)
        valid = list(valid_days(days, a.day_minimum))
        hive = f.stem.removeprefix("flow_")
        print(f"{hive}: {len(valid)} days from May to September, cap of {cap:.0f} per minute, "
              f"mean of {np.mean([m.sum() for _, m in valid]):.0f} crossings per day")
        for n in a.intervals:
            row = {"hive": hive, "days": len(valid), **compare(valid, n, a.hour_minimum)}
            print(row)
            rows.append(row)
    if a.csv:
        with open(a.csv, "w", newline="") as out:
            w = csv.DictWriter(out, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
