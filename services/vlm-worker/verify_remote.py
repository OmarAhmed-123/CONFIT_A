"""Verify the WORKER's `analyze_remote` Modal Function serves end-to-end via .remote().

This is production option (b): the backend calls the worker server-to-server over
Modal's internal channel (the container is held for the call, so the heavy cold start
is fine — unlike the stateless web edge). It exercises the ACTUAL worker class
(`load` @enter -> BF16 load, then `analyze_remote`), on a real A10G with real images
+ the real production prompts, with logs visible.

Run:  python3 services/vlm-worker/verify_remote.py
(NOT `modal run` — this is a __main__-driven app.run() + .remote() script.)
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modal_app  # noqa: E402

# EXACT production prompts (mirror backend/app/providers/tryon_provider.py).
VISION_PROMPT = (
    "Analyze this fashion image. Respond with STRICT JSON only, no prose, with keys: "
    "detected_category (one of: Outerwear, Tops, Bottoms, Dresses, Footwear, Accessories), "
    "detected_color (simple color family), detected_pattern, detected_style, "
    "detected_attributes (object of extra visible attributes). "
    "If the image does not show a fashion item, set detected_category to null."
)
WARDROBE_TAG_PROMPT = (
    "Analyze this photo of a clothing item the user owns. Respond with STRICT JSON only, "
    "no prose, with exactly these keys: category (one of: Tops, Bottoms, Outerwear, Footwear, "
    "Accessories, Dresses), item_type (specific subcategory, e.g. 'Oversized Blazer'), "
    "primary_color (simple color family name), primary_color_hex (approximate hex like #1B1F3B), "
    "secondary_colors (list, may be empty), style (short style description), style_tags (list up to 6), "
    "pattern (e.g. Solid, Striped, Checked, Floral), occasion_suitability (list), seasonality "
    "(one of: All-Season, Spring, Summer, Autumn, Winter), confidence (float 0.0-1.0). "
    "If the image does not show a clothing or fashion accessory item, set category to null."
)

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _b64(rel: str) -> str:
    with open(os.path.join(REPO, rel), "rb") as f:
        return base64.b64encode(f.read()).decode()


def main() -> None:
    cases = [
        ("blazer_person", "image/jpeg", VISION_PROMPT, "visual_search",
         "docs/VTON_PROOF_blazer_output_20260906.jpg"),
        ("garment_navy", "image/png", VISION_PROMPT, "visual_search",
         "services/vton-worker/_demo_inputs/garment_navy.png"),
    ]
    with modal_app.app.run():
        for name, mime, prompt, mode, rel in cases:
            print(f"[verify-remote {name}] calling vlm_analyze.remote() ...", flush=True)
            res = modal_app.vlm_analyze.remote(_b64(rel), mime, prompt, mode)
            print(f"[verify-remote {name} RESULT] {json.dumps(res)}", flush=True)


if __name__ == "__main__":
    main()
