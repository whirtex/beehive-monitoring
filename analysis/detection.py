"""Shared parts of the scripts: the detector, video reading and the comparison with the labels.

The detector is the YOLO11n of the Beehaviour project, trained on the Sledevic and
Matuzevicius dataset. The weights (21 MB, AGPL-3.0) are not in the repository; the
README explains how to download them.
"""

from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

FOLDER = Path(__file__).resolve().parent
WEIGHTS = FOLDER / "models" / "bee11n.pt"
DATA = FOLDER / "data" / "sledevic"
CONF = 0.40
# width of the station photos (OV2640 in SVGA, 800 x 600)
WIDTH = 800


def load_model(weights=WEIGHTS):
    from ultralytics import YOLO
    return YOLO(weights)


def detect(model, img, conf=CONF):
    """-> boxes (n x 5): x1, y1, x2, y2 and confidence."""
    r = model.predict(img, conf=conf, imgsz=640, verbose=False)[0]
    return np.column_stack((r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()))


def shrink(img, width=WIDTH):
    height = round(img.shape[0] * width / img.shape[1])
    return cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)


def video_frames(path, fps, start=0.0, duration=0.0):
    """Yields (second, image) at the requested rate, from `start`, for `duration` s (0 = to the end)."""
    cap = cv2.VideoCapture(str(path))
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(orig_fps / fps))
    i = round(start * orig_fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    end = i + round(duration * orig_fps) if duration else None
    while end is None or i < end:
        ok, img = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield i / orig_fps, img
        i += 1
    cap.release()


def iou(a, b):
    """IoU between every box of a (n x 4) and of b (m x 4)."""
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter)


def matches(det, labels, threshold=0.5):
    """Number of detections matched to a label by IoU, each label used once."""
    if len(det) == 0 or len(labels) == 0:
        return 0
    m = iou(det, labels)
    row, col = linear_sum_assignment(-m)
    return int(np.sum(m[row, col] >= threshold))


def metrics(pairs, threshold=0.5):
    """pairs: list of (detected boxes n x 4, labelled boxes m x 4), one per frame.

    Detection: precision, recall and F1 per box. Count: mean absolute error per
    frame, bias (detected minus labelled), relative error (mean error over the
    mean labelled count) and agreement, the R2 against the line y = x. The
    agreement falls with the bias; the r2 of the correlation does not, so it is
    not used.
    """
    tp = fp = fn = 0
    n_det, n_lab = [], []
    for det, lab in pairs:
        a = matches(det, lab, threshold)
        tp, fp, fn = tp + a, fp + len(det) - a, fn + len(lab) - a
        n_det.append(len(det))
        n_lab.append(len(lab))
    n_det, n_lab = np.array(n_det, float), np.array(n_lab, float)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "frames": len(pairs),
        "mean_labelled": n_lab.mean(),
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p + r else 0.0,
        "mean_error": np.mean(np.abs(n_det - n_lab)),
        "bias": np.mean(n_det - n_lab),
        "relative_error": np.mean(np.abs(n_det - n_lab)) / n_lab.mean(),
        "agreement": 1 - np.sum((n_det - n_lab) ** 2) / np.sum((n_lab - n_lab.mean()) ** 2),
    }


def line(name, m):
    return (f"{name}: {m['frames']} frames, {m['mean_labelled']:.1f} bees per frame | "
            f"precision {m['precision']:.3f}  recall {m['recall']:.3f}  F1 {m['f1']:.3f} | "
            f"error {m['mean_error']:.2f} ({100 * m['relative_error']:.0f}%), bias {m['bias']:+.2f}, "
            f"agreement {m['agreement']:.2f}")
