"""Simulates the station with a hive video, for presentations.

The station ESP32, running firmware/card_simulation, does everything as at the
hive except the photo: in place of the camera, this script plays the video in a
window and, every 10 s, sends the current frame over USB. The board writes the
photo to its card, with the DS3231 time, and a line to environment.csv with the
SIMULATED temperature and humidity sent with it (inside near 34.5 C, as in the
brood nest; outside near 27 C). The detector does not run here: it runs later,
in show-results.

At the end (time is up, or q or Esc in the window): unplug the station USB, take
the card out, put it in the computer card reader and run ./show-results.

Usage (in the beehive-monitoring folder), with the station plugged in:
    ./simulate               1 minute
    ./simulate 15            15 minutes (the video restarts when it ends)
    ./simulate 15 other.mp4  with another video
"""

import argparse
import glob
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import serial

from demo import panel
from detection import shrink, video_frames

FOLDER = Path(__file__).resolve().parent.parent
PHOTO_INTERVAL = 10
SPEED = 460800
CHUNK = 8192
NAME = "Bee station: simulation"


def open_board():
    ports = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.wchusbserial*") + glob.glob("/dev/cu.SLAB*")
                   + glob.glob("/dev/ttyUSB*"))
    if not ports:
        raise SystemExit("Board not found on USB. Plug in the station and try again.")
    s = serial.Serial(ports[0], SPEED, timeout=1)
    s.dtr = False
    s.rts = True
    time.sleep(0.1)
    s.rts = False  # restarts the board: the start goes to events.txt
    end = time.time() + 8
    while time.time() < end:
        line = s.readline().decode(errors="replace").strip()
        if line.startswith("SIMULATION READY"):
            return s
        if line.startswith("ERROR"):
            raise SystemExit(f"The board answered: {line}")
        if not line:
            s.write(b"PING\n")
    raise SystemExit("The board did not answer. Is it running firmware/card_simulation?")


def wait_for(s, start, seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        line = s.readline().decode(errors="replace").strip()
        if line.startswith(start) or line.startswith("ERROR"):
            return line
    return "ERROR the board did not answer"


def send_photo(s, jpg, ti, to, ho):
    s.reset_input_buffer()
    s.write(f"PHOTO {len(jpg)} {ti:.2f} {to:.1f} {ho:.0f}\n".encode())
    r = wait_for(s, "READY")
    if not r.startswith("READY"):
        return r
    for k in range(0, len(jpg), CHUNK):
        s.write(jpg[k:k + CHUNK])
        if s.read(1) != b"+":
            return "ERROR the board did not confirm a chunk"
    return wait_for(s, "OK")


def looped_frames(video, fps):
    while True:
        empty = True
        for _, img in video_frames(video, fps):
            empty = False
            yield img
        if empty:
            raise SystemExit(f"Could not read {video}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("minutes", type=float, nargs="?", default=1)
    p.add_argument("video", type=Path, nargs="?", default=FOLDER / "media" / "20230711a-fan.mp4")
    p.add_argument("--fps", type=float, default=10)
    a = p.parse_args()

    board = open_board()
    print("Station ready: sending a photo every 10 s to its card.")
    rng = np.random.default_rng()
    env = {"ti": 34.5, "to": 27.0, "ho": 70.0}
    state = {"photos": 0, "last": "", "busy": False}

    def send(img):
        env["ti"] = float(np.clip(env["ti"] + rng.normal(0, 0.05), 34.0, 35.0))
        env["to"] = env["to"] + rng.normal(0.01, 0.05)
        env["ho"] = float(np.clip(env["ho"] + rng.normal(0, 0.4), 55, 85))
        ok, jpg = cv2.imencode(".jpg", shrink(img), [cv2.IMWRITE_JPEG_QUALITY, 85])
        r = send_photo(board, jpg.tobytes(), env["ti"], env["to"], env["ho"])
        if r.startswith("OK"):
            state["photos"] += 1
            state["last"] = r[3:].strip()
            print(f"  {state['last']}  inside {env['ti']:.2f} C, outside {env['to']:.1f} C, {env['ho']:.0f} %")
        else:
            print("  " + r)
        state["busy"] = False

    cv2.namedWindow(NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(NAME, 1280, 720)
    clock = time.perf_counter()
    next_photo = 0.0
    for k, img in enumerate(looped_frames(a.video, a.fps)):
        elapsed = time.perf_counter() - clock
        if elapsed >= a.minutes * 60:
            break
        if elapsed >= next_photo and not state["busy"]:
            next_photo += PHOTO_INTERVAL
            state["busy"] = True
            threading.Thread(target=send, args=(img.copy(),), daemon=True).start()
        screen = shrink(img, 1280)
        left = max(0, a.minutes * 60 - elapsed)
        lines = [f"Photos written to the station card: {state['photos']}",
                 f"Left: {int(left // 60)}:{int(left % 60):02d}"]
        if state["last"]:
            lines.insert(1, f"Last: {state['last']}")
        panel(screen, lines)
        cv2.imshow(NAME, screen)
        wait = (k + 1) / a.fps - (time.perf_counter() - clock)
        if (cv2.waitKey(max(1, int(wait * 1000))) & 0xFF) in (ord("q"), 27):
            break
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    while state["busy"]:
        time.sleep(0.1)
    board.write(b"END\n")
    wait_for(board, "OK")
    board.close()
    print(f"\nDone: {state['photos']} photos on the station card.")
    print("Now: unplug the station USB, take the card out, put it in the computer reader and run ./show-results")


if __name__ == "__main__":
    main()
