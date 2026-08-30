"""PoseEstimationEngine — deterministic skeletal keypoints from bbox."""
from __future__ import annotations
import numpy as np
from PIL import Image


class PoseEstimationEngine:
    name = "pose-bbox-heuristic-v1"

    def __init__(self, **_):
        pass

    @staticmethod
    def _bbox_to_keypoints(bbox, image_size):
        x0, y0, x1, y1 = bbox
        w, h = image_size
        cx = (x0 + x1) / 2.0
        return {
            "nose": (cx, max(0, y0 + 0.05 * (y1 - y0))),
            "shoulders_mid": (cx, y0 + 0.20 * (y1 - y0)),
            "torso_mid": (cx, y0 + 0.45 * (y1 - y0)),
            "hip_mid": (cx, y0 + 0.65 * (y1 - y0)),
            "feet_mid": (cx, y0 + 0.95 * (y1 - y0)),
        }

    # new instance API
    def estimate(self, image, bbox):
        return PoseEstimationEngine.extract_pose(image, bbox=bbox)

    # legacy static API expected by worker.py + integrity tests
    @staticmethod
    def extract_pose(image: Image.Image, bbox=None) -> dict:
        # if no bbox supplied, derive from luminance (real)
        if bbox is None:
            rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
            luminance = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
            mask = luminance < float(luminance.mean())
            ys, xs = np.where(mask)
            if len(xs) == 0:
                bbox = (0, 0, image.width - 1, image.height - 1)
            else:
                bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        kp = PoseEstimationEngine._bbox_to_keypoints(bbox, image.size)
        x0, y0, x1, y1 = bbox
        return {
            "engine": PoseEstimationEngine.name,
            "keypoints": kp,
            "shoulder_width_px": float(max(8.0, 0.40 * (x1 - x0))),
            "image_size": image.size,
            "bbox": bbox,
        }
