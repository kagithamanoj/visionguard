"""Generate synthetic inspection images for VisionGuard.

Creates two classes of 640x480 images in samples/:
  clean    - a metal plate with light texture noise, no defects
  defective - the same plate with scratches, dents, or spots drawn on it

Also writes samples/labels.csv mapping filename -> label.
Run: python scripts/make_sample_images.py [--count N] [--out DIR]
"""
import argparse
import csv
import os

import cv2
import numpy as np

IMG_W, IMG_H = 640, 480
PLATE = (200, 205, 210)  # light gray metal plate
BG = (60, 60, 60)        # dark background


def _base_plate(rng):
    img = np.full((IMG_H, IMG_W, 3), BG, dtype=np.uint8)
    # plate rectangle with a small margin
    x0, y0, x1, y1 = 90, 70, 550, 410
    img[y0:y1, x0:x1] = PLATE
    # light texture noise inside the plate
    noise = rng.integers(-12, 13, size=(y1 - y0, x1 - x0, 3), dtype=np.int16)
    plate = img[y0:y1, x0:x1].astype(np.int16) + noise
    img[y0:y1, x0:x1] = np.clip(plate, 0, 255).astype(np.uint8)
    # corner bolt holes: dark bore with a bright machined ring
    for cx, cy in [(130, 110), (510, 110), (130, 370), (510, 370)]:
        cv2.circle(img, (cx, cy), 14, (40, 40, 40), -1)
        cv2.circle(img, (cx, cy), 14, (235, 235, 235), 2)
    return img, (x0, y0, x1, y1)


def _scratch(img, plate_box, rng):
    x0, y0, x1, y1 = plate_box
    x_start = int(rng.integers(x0 + 30, x0 + 120))
    y_start = int(rng.integers(y0 + 40, y1 - 40))
    pts = [(x_start, y_start)]
    x, y = x_start, y_start
    for _ in range(int(rng.integers(6, 12))):
        x += int(rng.integers(20, 45))
        y += int(rng.integers(-14, 15))
        pts.append((x, y))
    cv2.polylines(img, [np.array(pts, dtype=np.int32)], False, (45, 45, 45),
                  thickness=int(rng.integers(3, 6)))
    return img


def _dent(img, plate_box, rng):
    x0, y0, x1, y1 = plate_box
    cx = int(rng.integers(x0 + 80, x1 - 80))
    cy = int(rng.integers(y0 + 60, y1 - 60))
    axes = (int(rng.integers(25, 60)), int(rng.integers(15, 35)))
    angle = int(rng.integers(0, 180))
    cv2.ellipse(img, (cx, cy), axes, angle, 0, 360, (70, 70, 70), -1)
    cv2.ellipse(img, (cx, cy), (axes[0] - 8, axes[1] - 8), angle, 0, 360,
                (110, 110, 110), -1)
    return img


def _spots(img, plate_box, rng):
    x0, y0, x1, y1 = plate_box
    for _ in range(int(rng.integers(3, 7))):
        cx = int(rng.integers(x0 + 40, x1 - 40))
        cy = int(rng.integers(y0 + 40, y1 - 40))
        r = int(rng.integers(5, 14))
        cv2.circle(img, (cx, cy), r, (50, 50, 50), -1)
    return img


DEFECT_FNS = {"scratch": _scratch, "dent": _dent, "spots": _spots}


def generate(count, out_dir, seed=42):
    rng = np.random.default_rng(seed)
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    defect_kinds = list(DEFECT_FNS)
    for i in range(count):
        kind = defect_kinds[i % len(defect_kinds)]
        img, plate_box = _base_plate(rng)
        img = DEFECT_FNS[kind](img, plate_box, rng)
        name = f"defective_{kind}_{i:03d}.png"
        cv2.imwrite(os.path.join(out_dir, name), img)
        rows.append((name, "defective"))
    for i in range(count):
        img, _ = _base_plate(rng)
        name = f"clean_{i:03d}.png"
        cv2.imwrite(os.path.join(out_dir, name), img)
        rows.append((name, "clean"))
    with open(os.path.join(out_dir, "labels.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "label"])
        w.writerows(rows)
    print(f"wrote {len(rows)} images + labels.csv to {out_dir}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=20,
                   help="images per class")
    p.add_argument("--out", default="samples")
    a = p.parse_args()
    generate(a.count, a.out)
