"""Draws the two figures of the article.

- assets/architecture.pdf (and .png, for the README): the processing chain.
- assets/prototype-and-detections.jpg: (a) the station assembled on the bench and
  (b) the YOLO11n detections on a frame of a hive left out of training, at the
  width of the station photos.

Usage (in the beehive-monitoring folder):
    .venv/bin/python analysis/figures.py
"""

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from detection import DATA, FOLDER, detect, load_model, shrink  # noqa: E402

ASSETS = FOLDER.parent / "assets"
INK = "#0b0b0b"
INK_2 = "#52514e"
EDGE = "#9a9892"
HIVE_BG = "#f1f0ec"
PC_BG = "#eaf2fb"
YELLOW = (0, 220, 255)  # BGR

BLOCKS = [
    # (x, title, lines, background)
    (0.0, "Sensors", ["OV2640", "DS18B20 in", "AHT20 out"], HIVE_BG),
    (2.35, "ESP32", ["1 photo / 10 s,", "06:00-18:00;", "CSV: 5 min"], HIVE_BG),
    (4.7, "microSD", ["JPEG photos", "and CSV,", "DS3231 time"], "#ffffff"),
    (7.05, "Detector", ["YOLO11n,", "bees per photo"], PC_BG),
    (9.4, "Record", ["median per", "5 min with", "temperature"], PC_BG),
]
BLOCK_W = 2.0
BLOCK_H = 2.3
# frame of panel (b): hive left out of training, with bees in the slot and on the board
FRAME_B = ("20230711b", "20230711b6360")
PANEL_H = 540


def architecture():
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    fig, ax = plt.subplots(figsize=(3.45, 1.05))
    ax.set_xlim(-0.05, 11.45)
    ax.set_ylim(-0.5, BLOCK_H + 0.05)
    ax.axis("off")
    for x, title, lines, bg in BLOCKS:
        ax.add_patch(FancyBboxPatch((x, 0), BLOCK_W, BLOCK_H, boxstyle="round,pad=0,rounding_size=0.12",
                                    facecolor=bg, edgecolor=EDGE, linewidth=0.9))
        ax.text(x + BLOCK_W / 2, BLOCK_H - 0.4, title, ha="center", va="center",
                fontsize=6.6, fontweight="bold", color=INK)
        for i, l in enumerate(lines):
            ax.text(x + BLOCK_W / 2, BLOCK_H - 1.0 - 0.45 * i, l, ha="center", va="center", fontsize=5.4, color=INK_2)
    for x, _, _, _ in BLOCKS[:-1]:
        ax.add_patch(FancyArrowPatch((x + BLOCK_W + 0.04, BLOCK_H / 2), (x + 2.35 - 0.04, BLOCK_H / 2),
                                     arrowstyle="-|>", mutation_scale=6, color=INK_2, linewidth=1))
    ax.text(2.35 + BLOCK_W / 2, -0.3, "at the hive, on solar power", ha="center", fontsize=5.4, color=INK_2,
            style="italic")
    ax.text(7.05 + (2.35 + BLOCK_W) / 2, -0.3, "offline, after each card retrieval", ha="center", fontsize=5.4,
            color=INK_2, style="italic")
    fig.tight_layout(pad=0.1)
    # no date in the PDF, so the file only changes when the drawing changes
    fig.savefig(ASSETS / "architecture.pdf", bbox_inches="tight", pad_inches=0.01, metadata={"CreationDate": None})
    fig.savefig(ASSETS / "architecture.png", dpi=300, bbox_inches="tight", pad_inches=0.01)
    plt.close(fig)


def label(img, text):
    font = cv2.FONT_HERSHEY_DUPLEX
    (w, h), _ = cv2.getTextSize(text, font, 1.3, 2)
    cv2.rectangle(img, (0, 0), (w + 24, h + 24), (255, 255, 255), -1)
    cv2.putText(img, text, (12, h + 12), font, 1.3, (0, 0, 0), 2, cv2.LINE_AA)


def prototype_and_detections():
    a = cv2.imread(str(ASSETS / "station-side.jpg"))
    a = a[150:1260, 420:1900]  # the whole station, with the clock, without the keyboard above
    hive, name = FRAME_B
    b = shrink(cv2.imread(str(DATA / "detection" / f"_bee_{hive}" / "images" / f"{name}.jpg")))
    for x1, y1, x2, y2 in detect(load_model(), b)[:, :4].astype(int):
        cv2.rectangle(b, (x1, y1), (x2, y2), YELLOW, 2)
    panels = []
    for img, text in ((a, "(a)"), (b, "(b)")):
        img = cv2.resize(img, (round(img.shape[1] * PANEL_H / img.shape[0]), PANEL_H), interpolation=cv2.INTER_AREA)
        label(img, text)
        panels.append(img)
    white = np.full((PANEL_H, 16, 3), 255, np.uint8)
    cv2.imwrite(str(ASSETS / "prototype-and-detections.jpg"), np.hstack([panels[0], white, panels[1]]),
                [cv2.IMWRITE_JPEG_QUALITY, 90])


def main():
    architecture()
    prototype_and_detections()
    print("assets/architecture.pdf, assets/architecture.png, assets/prototype-and-detections.jpg")


if __name__ == "__main__":
    main()
