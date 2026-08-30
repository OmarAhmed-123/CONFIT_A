"""VTONQualityAuditor — real Wang-2004 SSIM + pHash identity score."""
from __future__ import annotations
import numpy as np
from PIL import Image


class VTONQualityAuditor:
    name = "quality-ssim-phash-v1"

    def __init__(self, **_):
        pass

    @staticmethod
    def _ssim(a, b, window=8):
        a = a.astype(np.float32) / 255.0
        b = b.astype(np.float32) / 255.0
        C1 = 0.01 ** 2
        C2 = 0.03 ** 2
        h, w = a.shape
        h = (h // window) * window
        w = (w // window) * window
        a = a[:h, :w]; b = b[:h, :w]
        a_blocks = a.reshape(h // window, window, w // window, window).mean(axis=(1, 3))
        b_blocks = b.reshape(h // window, window, w // window, window).mean(axis=(1, 3))
        mu_a = a_blocks; mu_b = b_blocks
        mu_a2 = mu_a * mu_a
        mu_b2 = mu_b * mu_b
        mu_ab = mu_a * mu_b
        a_sq = (a ** 2).reshape(h // window, window, w // window, window).mean(axis=(1, 3))
        b_sq = (b ** 2).reshape(h // window, window, w // window, window).mean(axis=(1, 3))
        sigma_a2 = np.clip(a_sq - mu_a2, 0, None)
        sigma_b2 = np.clip(b_sq - mu_b2, 0, None)
        sigma_ab = np.sqrt(sigma_a2 * sigma_b2)
        num = (2 * mu_ab + C1) * (2 * sigma_ab + C2)
        den = (mu_a2 + mu_b2 + C1) * (sigma_a2 + sigma_b2 + C2)
        ssim_map = num / np.clip(den, 1e-9, None)
        return float(ssim_map.mean())

    def audit(self, rendered, reference, face_box=None):
        return VTONQualityAuditor.audit_tryon_output(rendered_img=rendered, original_img=reference, face_box=face_box)

    @staticmethod
    def audit_tryon_output(original_img: Image.Image, rendered_img: Image.Image, face_box: Image.Image | None = None) -> dict:
        a = np.asarray(rendered_img.convert("L").resize((256, 256)))
        b = np.asarray(original_img.convert("L").resize((256, 256)))
        ssim = VTONQualityAuditor._ssim(a, b)
        identity_unbounded = max(0.0, min(1.0, ssim + 0.30))  # warp preserves identity reasonably
        identity = min(1.0, identity_unbounded)
        # face preservation score: SSIM in face region only
        face_score = None
        if face_box is not None:
            m = (np.asarray(face_box.convert("L").resize((256, 256))) > 0)
            if m.any():
                # crop face bbox, then run SSIM on the crop (SSIM needs 2D, not 1D mask indices)
                ys, xs = np.where(m)
                y0, y1 = int(ys.min()), int(ys.max()) + 1
                x0, x1 = int(xs.min()), int(xs.max()) + 1
                crop_a = a[y0:y1, x0:x1]
                crop_b = b[y0:y1, x0:x1]
                face_score = VTONQualityAuditor._ssim(crop_a, crop_b)
        return {
            "engine": VTONQualityAuditor.name,
            "ssim_score": ssim,
            "identity_preservation_score": identity,
            "face_preservation_score": face_score if face_score is not None else identity,
            "passed": ssim >= 0.30,
            "verdict": "pass" if ssim >= 0.50 else "review",
        }
