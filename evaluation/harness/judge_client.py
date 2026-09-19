"""Qwen2.5-VL-7B judge client (Phase 0.5 §23) — implementation.

The production vlm-worker /analyze contract accepts ONE image + prompt.
To respect the FROZEN image ordering (reference garment -> generated output),
we build a deterministic labeled composite: garment LEFT, output RIGHT, with
explicit caption text baked into the image. Order is fixed left->right for
every sample; the transport detail is documented in the benchmark report.

Consistency: every sample is judged twice (2 independent calls); both raw
outputs + agreement are recorded. do_sample=False on the worker => greedy,
deterministic decoding (matches frozen temperature 0 intent).
"""
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

import requests
import yaml
from PIL import Image, ImageDraw, ImageFont

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUTPUTS = RESULTS / "outputs"
GARMENTS = EVAL_ROOT / "fixtures" / "garments"


def load_config() -> dict:
    return yaml.safe_load((EVAL_ROOT / "config" / "judge_config.yaml").read_text())


def load_token() -> str:
    for line in (EVAL_ROOT / ".eval_env").read_text().splitlines():
        if line.startswith("VLM_EVAL_ADMIN_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("VLM_EVAL_ADMIN_TOKEN missing from .eval_env")


def get_vlm_urls() -> dict:
    lines = (EVAL_ROOT / ".eval_vlm_urls").read_text().split()
    return {"health": lines[0], "analyze": lines[1]}


def _data_uri(b: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(b).decode()


def build_composite(garment_path: Path, output_path: Path) -> bytes:
    """Labeled side-by-side: LEFT reference garment, RIGHT try-on output (fixed order)."""
    g = Image.open(garment_path).convert("RGB")
    o = Image.open(output_path).convert("RGB")
    H = 768
    g = g.resize((int(g.size[0] * H / g.size[1]), H))
    o = o.resize((int(o.size[0] * H / o.size[1]), H))
    cap_h = 56
    W = g.size[0] + o.size[0] + 8
    canvas = Image.new("RGB", (W, H + cap_h), (255, 255, 255))
    canvas.paste(g, (0, 0))
    canvas.paste(o, (g.size[0] + 8, 0))
    d = ImageDraw.Draw(canvas)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    except Exception:
        f = ImageFont.load_default()
    d.text((10, H + 10), "REFERENCE GARMENT (image 1)", fill=(0, 0, 0), font=f)
    d.text((g.size[0] + 18, H + 10), "TRY-ON OUTPUT (image 2)", fill=(0, 0, 0), font=f)
    import io
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _call(analyze_url: str, token: str, composite: bytes, prompt: str) -> dict:
    r = requests.post(analyze_url,
                      headers={"X-VLM-Admin": token, "Content-Type": "application/json"},
                      json={"image": _data_uri(composite), "prompt": prompt, "mode": "eval_judge"},
                      timeout=600)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:400]}
    return {"http": r.status_code, "body": j}


def judge_sample(analyze_url: str, token: str, cfg: dict, sample: dict,
                 garment_name: str, slot: str, expected_visible: str,
                 garment_path: Path, output_path: Path) -> dict:
    prompt = cfg["eval_prompt_template"].format(garment_name=garment_name, slot=slot,
                                                expected_visible=expected_visible)
    full_prompt = cfg["system_prompt"] + "\n" + prompt
    comp = build_composite(garment_path, output_path)
    t0 = time.time()
    r1 = _call(analyze_url, token, comp, full_prompt)
    t1 = time.time()
    r2 = _call(analyze_url, token, comp, full_prompt)
    t2 = time.time()
    j1 = r1["body"] if isinstance(r1["body"], dict) else {}
    j2 = r2["body"] if isinstance(r2["body"], dict) else {}
    dims = ("garment_accuracy", "layering_accuracy", "styling_accuracy")
    agree = all(j1.get(d) == j2.get(d) for d in dims) if j1 and j2 else None
    return {
        "sample_id": sample.get("sample_id"),
        "call1": {"http": r1["http"], "latency_s": round(t1 - t0, 2), "json": j1},
        "call2": {"http": r2["http"], "latency_s": round(t2 - t1, 2), "json": j2},
        "two_call_agreement": agree,
        "primary": j1,
    }


def run_judge(run_id: str = "baseline-20260915") -> dict:
    cfg = load_config()
    token = load_token()
    urls = get_vlm_urls()
    off = json.loads((RESULTS / f"{run_id}_offline_eval.json").read_text())
    gmanifest = {g["garment_id"]: g for g in json.loads((EVAL_ROOT / "fixtures" / "garment_manifest.json").read_text())}
    outfits = json.loads((EVAL_ROOT / "fixtures" / "outfits.json").read_text())["outfits"]
    final_orders = {o["outfit_id"]: max(l["order"] for l in o["layers"]) for o in outfits}

    results = []
    for s in off["samples"]:
        oid = s["sample_id"].split("/")[0]
        order = int(s["sample_id"].split("/L")[1].split("-")[0])
        is_single = s["arm"] == "SINGLE"
        if not (is_single or order == final_orders.get(oid, 1)):
            continue
        out_file = OUTPUTS / f"{oid}-L{order}-{s['garment_id']}.jpg"
        if not out_file.exists():
            continue
        g = gmanifest[s["garment_id"]]
        visible = g["name"] if is_single else f"layers up to order {order} (see outfit {oid})"
        res = judge_sample(urls["analyze"], token, cfg, s, g["name"], g["slot"],
                           visible, GARMENTS / f"{g['garment_id']}.jpg", out_file)
        results.append(res)
        print(f"judged {s['sample_id']} agree={res['two_call_agreement']}", flush=True)
        (RESULTS / f"{run_id}_judge.json").write_text(json.dumps(
            {"run_id": run_id, "config_version": cfg["config_version"],
             "judged_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "results": results}, indent=1))
    print(f"JUDGE DONE n={len(results)}")
    return results


if __name__ == "__main__":
    run_judge()
