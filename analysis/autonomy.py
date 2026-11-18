"""Computes the daily consumption of the station and its autonomy with the solar panel and the battery.

The default values are estimates, not measurements: replace them with the ones
measured in series with the 5 V supply, in each state of the board. The bench
measured 0.6 s awake per photo. The calculation assumes that the board sleeps
(deep sleep) between photos and also wakes every 5 min to read the sensors.

Usage (in the beehive-monitoring folder):
    .venv/bin/python analysis/autonomy.py
    .venv/bin/python analysis/autonomy.py --photo-ma 210 --photo-s 0.6 --sleep-ma 7
"""

import argparse

V = 5.0  # voltage at the board input


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--photo-ma", type=float, default=180, help="current while awake, taking and writing the photo")
    p.add_argument("--photo-s", type=float, default=1.5, help="time awake per photo, with the camera start-up")
    p.add_argument("--sensors-ma", type=float, default=50, help="current while reading the sensors")
    p.add_argument("--sensors-s", type=float, default=1.0)
    p.add_argument("--sleep-ma", type=float, default=10,
                   help="board asleep; on the development board, the USB converter, the regulator and the LED")
    p.add_argument("--interval-s", type=float, default=10, help="one photo every N seconds")
    p.add_argument("--camera-hours", type=float, default=12, help="06:00 to 18:00")
    p.add_argument("--boost", type=float, default=0.85, help="efficiency of the 5 V regulator")
    p.add_argument("--battery-wh", type=float, default=11.1 * 0.8, help="18650 of 3000 mAh, 80%% usable")
    p.add_argument("--panel-w", type=float, default=3.0)
    p.add_argument("--sun-h", type=float, default=4.5, help="peak sun hours per day")
    p.add_argument("--charge", type=float, default=0.7, help="efficiency from the panel to the battery")
    a = p.parse_args()

    photos = a.camera_hours * 3600 / a.interval_s
    readings = 24 * 60 / 5
    wh_photos = photos * a.photo_s * a.photo_ma / 1000 * V / 3600
    wh_sensors = readings * a.sensors_s * a.sensors_ma / 1000 * V / 3600
    wh_sleep = 24 * a.sleep_ma / 1000 * V
    wh_day = (wh_photos + wh_sensors + wh_sleep) / a.boost
    wh_panel = a.panel_w * a.sun_h * a.charge

    print(f"{photos:.0f} photos and {readings:.0f} readings per day")
    print(f"photos {wh_photos:.2f} Wh, sensors {wh_sensors:.2f} Wh, asleep {wh_sleep:.2f} Wh "
          f"-> {wh_day:.2f} Wh per day drawn from the battery")
    print(f"without sun, the battery lasts {a.battery_wh / wh_day:.1f} days")
    print(f"the panel restores {wh_panel:.1f} Wh on a sunny day, {wh_panel / wh_day:.1f} times the consumption")


if __name__ == "__main__":
    main()
