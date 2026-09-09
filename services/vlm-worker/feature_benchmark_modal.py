"""REAL feature validation of Qwen2.5-VL-7B on real fashion images (single GPU run).

Loads the model once, then runs the ACTUAL production prompts (VISION_PROMPT for
visual search, WARDROBE_TAG_PROMPT for wardrobe auto-tagging) on real CONFIT_A
images, measuring per-case generation latency + peak VRAM. Prints the real
extracted attributes. This is a measured product benchmark, not a generic one.

Run:  modal run services/vlm-worker/feature_benchmark_modal.py
"""
import base64
import io
import json
import os
import re
import time

import modal

app = modal.App("confit-vlm-feature")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgomp1", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch", "torchvision", "transformers>=4.50.0", "accelerate>=0.33.0",
        "qwen-vl-utils>=0.0.8", "huggingface_hub>=0.24.0", "Pillow>=10.4.0", "numpy>=1.26.0",
    )
)
vol = modal.Volume.from_name("confit-qwen25vl-weights")

# EXACT production prompts (mirror backend/app/providers/tryon_provider.py)
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


def _extract_json(raw: str):
    if not raw:
        return None
    text = raw
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        s, e = text.find("{"), text.rfind("}")
        if s == -1 or e <= s:
            return None
        text = text[s : e + 1]
    try:
        return json.loads(text)
    except Exception:
        return {"_unparsed": raw[:300]}


@app.function(gpu="A10G", image=image, volumes={"/weights": vol}, timeout=1500)
def run(cases):
    import torch
    from PIL import Image
    from qwen_vl_utils import process_vision_info
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    os.environ.setdefault("QWEN_VL_WEIGHTS_DIR", "/weights")
    t0 = time.time()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        "/weights", torch_dtype=torch.bfloat16, device_map="auto"
    ).eval()
    proc = AutoProcessor.from_pretrained("/weights")
    load_s = time.time() - t0
    print(f"[feat] dev={torch.cuda.get_device_name(0)} LOAD {load_s:.1f}s "
          f"VRAM={torch.cuda.memory_allocated() / 1024**3:.2f}GiB", flush=True)

    prompts = {"vision": VISION_PROMPT, "wardrobe": WARDROBE_TAG_PROMPT}
    out = []
    for i, c in enumerate(cases):
        pil = Image.open(io.BytesIO(base64.b64decode(c["b64"]))).convert("RGB")
        prompt = prompts[c["kind"]]
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": pil}, {"type": "text", "text": prompt},
        ]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ii, vi = process_vision_info(msgs)
        inputs = proc(text=[text], images=ii, videos=vi, padding=True, return_tensors="pt").to(model.device)
        il = inputs["input_ids"].shape[1]
        t0 = time.time()
        with torch.inference_mode():
            g = model.generate(**inputs, max_new_tokens=300, do_sample=False)
        dt = time.time() - t0
        raw = proc.batch_decode(g[:, il:], skip_special_tokens=True)[0]
        parsed = _extract_json(raw)
        rec = {"case": c["name"], "kind": c["kind"], "gen_s": round(dt, 2),
               "vram_gib": round(torch.cuda.memory_allocated() / 1024**3, 2),
               "parsed": parsed}
        out.append(rec)
        print(f"[feat] {c['name']} ({c['kind']}) gen={dt:.2f}s "
              f"VRAM={rec['vram_gib']}GiB -> {json.dumps(parsed)[:400]}", flush=True)
    return {"load_s": round(load_s, 1), "results": out}


if __name__ == "__main__":
    # Repo root = two levels up from services/vlm-worker (no hard-coded local path).
    IMGDIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    tests = [
        ("services/vton-worker/_demo_inputs/garment_navy.png", "garment_navy", "vision"),
        ("services/vton-worker/_demo_inputs/garment_navy.png", "garment_navy_wardrobe", "wardrobe"),
        ("docs/VTON_PROOF_blazer_output_20260906.jpg", "blazer_person", "vision"),
    ]
    cases = [
        {"name": n, "kind": k, "b64": base64.b64encode(open(os.path.join(IMGDIR, p), "rb").read()).decode()}
        for p, n, k in tests
    ]
    with app.run():
        result = run.remote(cases)
    print(json.dumps(result, indent=2))
