"""GarmentPreprocessor — background-colour trim + RGBA pack."""
from __future__ import annotations
import numpy as np
from PIL import Image


class GarmentPreprocessor:
    name = "garment-bgcolor-trim-v1"

    SUPPORTED_SLOTS = ("upper_outer", "upper_inner", "lower", "dress", "footwear", "accessory")

    def __init__(self, **_):
        pass

    @staticmethod
    def _bg_color(rgb: np.ndarray) -> np.ndarray:
        border = np.concatenate([
            rgb[0, :].reshape(-1, 3), rgb[-1, :].reshape(-1, 3),
            rgb[:, 0].reshape(-1, 3), rgb[:, -1].reshape(-1, 3),
        ], axis=0)
        return np.median(border, axis=0).astype(np.float32)

    def preprocess(self, image, product_id=1, slot_type="upper_outer"):
        return GarmentPreprocessor.preprocess_garment(image, product_id, slot_type)

    @staticmethod
    def preprocess_garment(image: Image.Image, product_id=1, slot_type="upper_outer") -> tuple:
        if slot_type not in GarmentPreprocessor.SUPPORTED_SLOTS:
            raise ValueError(f"unsupported garment slot_type={slot_type!r}; expected one of {GarmentPreprocessor.SUPPORTED_SLOTS}")
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        bg = GarmentPreprocessor._bg_color(rgb)
        diff = np.linalg.norm(rgb - bg[None, None, :], axis=2)
        mask = (diff > 0.10).astype(np.uint8) * 255
        ys, xs = np.where(mask > 0)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if len(xs) else (0, 0, image.width - 1, image.height - 1)
        garment_rgba = image.convert("RGBA")
        garment_rgba.putalpha(Image.fromarray(mask, mode="L").resize(image.size, Image.BILINEAR))
        pack = {
            "engine": GarmentPreprocessor.name,
            "product_id": product_id,
            "slot_type": slot_type,
            "bbox": bbox,
            "foreground_pixels": int((mask > 0).sum()),
            "background_color_rgb": [float(c) for c in bg.tolist()],
        }
        # legacy tuple shape: (garment_rgb, garment_alpha, garment_pack)
        return garment_rgba.convert("RGB"), garment_rgba.split()[-1], pack
