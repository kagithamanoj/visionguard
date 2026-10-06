"""Detection agent: finds surface defects on metal plates with classical CV.

Pipeline: grayscale -> Gaussian blur -> plate segmentation -> dark-anomaly
search inside the plate -> mounting-hole rejection -> scored detections.

No learned model is needed here. The detector works on any image where the
plate is brighter than the background and defects are darker than the plate.
"""
import os
from dataclasses import dataclass, asdict
from typing import List, Tuple

import cv2
import numpy as np


@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    area: float
    defect_score: float  # 0.0 (clean) .. 1.0 (severe)
    label: str           # scratch | dent | spot

    def to_dict(self):
        d = asdict(self)
        d["bbox"] = list(d["bbox"])
        return d


class DetectorAgent:
    def __init__(self,
                 blur_kernel: int = 5,
                 plate_threshold: int = 120,
                 defect_contrast: int = 40,
                 min_area: float = 80.0,
                 max_area: float = 20000.0,
                 hole_circularity: float = 0.75,
                 ring_brightness_margin: float = 5.0):
        self.blur_kernel = blur_kernel
        self.plate_threshold = plate_threshold
        self.defect_contrast = defect_contrast
        self.min_area = min_area
        self.max_area = max_area
        self.hole_circularity = hole_circularity
        self.ring_brightness_margin = ring_brightness_margin

    def _plate_mask(self, gray: np.ndarray):
        """Binary mask of the bright plate region."""
        _, mask = cv2.threshold(gray, self.plate_threshold, 255,
                                cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        plate = max(contours, key=cv2.contourArea)
        if cv2.contourArea(plate) < 1000:
            return None
        filled = np.zeros_like(mask)
        cv2.drawContours(filled, [plate], -1, 255, -1)
        return filled

    def _is_mounting_hole(self, contour, gray, plate_mean) -> bool:
        """Mounting holes are near-circular and carry a bright machined ring."""
        area = cv2.contourArea(contour)
        perim = cv2.arcLength(contour, True)
        if perim == 0:
            return False
        circularity = 4 * np.pi * area / (perim * perim)
        if circularity < self.hole_circularity:
            return False
        mask = np.zeros_like(gray)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        kernel = np.ones((7, 7), np.uint8)
        ring = cv2.dilate(mask, kernel) - mask
        ring_mean = cv2.mean(gray, mask=ring)[0]
        return ring_mean > plate_mean + self.ring_brightness_margin

    def detect(self, image_path: str) -> List[Detection]:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"image not found: {image_path}")
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"could not decode image: {image_path}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_kernel, self.blur_kernel), 0)

        plate_mask = self._plate_mask(gray)
        if plate_mask is None:
            return []

        plate_mean = cv2.mean(gray, mask=plate_mask)[0]
        dark = np.zeros_like(gray)
        dark[(gray < plate_mean - self.defect_contrast) &
             (plate_mask > 0)] = 255

        contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        detections = []
        for c in contours:
            area = cv2.contourArea(c)
            if not (self.min_area <= area <= self.max_area):
                continue
            if self._is_mounting_hole(c, gray, plate_mean):
                continue
            x, y, w, h = cv2.boundingRect(c)
            blob_mask = np.zeros_like(gray)
            cv2.drawContours(blob_mask, [c], -1, 255, -1)
            blob_mean = cv2.mean(gray, mask=blob_mask)[0]
            contrast = (plate_mean - blob_mean) / max(plate_mean, 1.0)
            score = float(np.clip(contrast * 1.25, 0.0, 1.0))
            (_, _), (rw, rh), _ = cv2.minAreaRect(c)
            aspect = max(rw, rh) / max(min(rw, rh), 1.0)
            if aspect > 4.0:
                label = "scratch"
            elif area > 1500:
                label = "dent"
            else:
                label = "spot"
            detections.append(Detection(bbox=(x, y, w, h), area=float(area),
                                        defect_score=score, label=label))
        detections.sort(key=lambda d: d.defect_score, reverse=True)
        return detections


def main():
    import argparse
    import json
    p = argparse.ArgumentParser()
    p.add_argument("image")
    a = p.parse_args()
    agent = DetectorAgent()
    for d in agent.detect(a.image):
        print(json.dumps(d.to_dict()))


if __name__ == "__main__":
    main()
