"""LightingHarmonizer — histogram CDF matching into reference tone."""
from __future__ import annotations
import numpy as np
from PIL import Image


class LightingHarmonizer:
    name = "harmonize-histogram-match-v1"

    def __init__(self, **_):
        pass

    @staticmethod
    def _match(src, ref, bins=64):
        s_hist, edges = np.histogram(src, bins=bins, range=(0.0, 1.0))
        r_hist, _ = np.histogram(ref, bins=bins, range=(0.0, 1.0))
        s_cdf = np.cumsum(s_hist) / max(1, s_hist.sum())
        r_cdf = np.cumsum(r_hist) / max(1, r_hist.sum())
        ref_values = (edges[:-1] + edges[1:]) / 2.0
        mapping = np.interp(s_cdf, r_cdf, ref_values)
        idx = np.clip(np.digitize(src, edges) - 1, 0, bins - 1)
        return mapping[idx]

    def harmonize(self, composite, reference, mask=None):
        return LightingHarmonizer.harmonize_lighting(composite, reference, mask)

    @staticmethod
    def harmonize_lighting(composite: Image.Image, reference: Image.Image, mask: Image.Image | None = None) -> Image.Image:
        comp = np.asarray(composite.convert("RGB"), dtype=np.float32) / 255.0
        ref  = np.asarray(reference.convert("RGB"), dtype=np.float32) / 255.0
        m = None
        if mask is not None:
            m = (np.asarray(mask.convert("L"), dtype=np.float32) / 255.0) > 0.5
        Y_C = 0.299 * comp[..., 0] + 0.587 * comp[..., 1] + 0.114 * comp[..., 2]
        Y_R = 0.299 * ref[..., 0]  + 0.587 * ref[..., 1]  + 0.114 * ref[..., 2]
        new_Y = Y_C.copy()
        if m is None:
            new_Y = LightingHarmonizer._match(Y_C.reshape(-1), Y_R.reshape(-1)).reshape(comp.shape[:2])
        else:
            if m.any():
                new_Y[m] = LightingHarmonizer._match(Y_C[m], Y_R.reshape(-1))
        scale = np.divide(new_Y, np.clip(Y_C, 1e-6, None),
                          out=np.ones_like(new_Y, dtype=np.float32),
                          where=Y_C > 1e-6).astype(np.float32)
        out = np.clip(comp * scale[..., None], 0.0, 1.0)
        return Image.fromarray(np.clip(out * 255.0, 0, 255).astype(np.uint8), mode="RGB")
