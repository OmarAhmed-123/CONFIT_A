#!/usr/bin/env python3
"""Live watsonx.ai connectivity + model smoke test (operator tool, not CI).

Usage:  set -a && source .env && set +a && PYTHONPATH=. python scripts/watsonx_smoke.py [image.jpg]

Checks, in order, and prints PASS/FAIL per step without ever printing the key:
  1. IAM token exchange
  2. configured REASONING model answers a strict-JSON prompt
  3. configured VISION model describes an image (a synthetic garment if no path given)
  4. the full WardrobeStylistService prompt round-trip against a synthetic closet
Exit code 0 only if every step passed.
"""
from __future__ import annotations

import asyncio
import io
import json
import sys

from PIL import Image, ImageDraw

from backend.app.core.config import settings
from backend.app.providers.watsonx.client import WatsonxClient, WatsonxError, redact
from backend.app.providers.watsonx.prompts import STYLIST_SYSTEM_PROMPT, build_stylist_user_message
from backend.app.providers.watsonx.vision import WatsonxVisionProvider, parse_vision_json


def _synthetic_shirt() -> bytes:
    img = Image.new("RGB", (512, 512), (245, 245, 245))
    d = ImageDraw.Draw(img)
    d.rectangle([140, 80, 372, 460], fill=(30, 60, 120))
    d.rectangle([80, 80, 180, 240], fill=(30, 60, 120))
    d.rectangle([332, 80, 432, 240], fill=(30, 60, 120))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def main(image_path: str | None) -> int:
    ok = True
    print(f"watsonx url={settings.WATSONX_URL} project={redact(settings.WATSONX_PROJECT_ID)} key={redact(settings.WATSONX_APIKEY)}")
    client = WatsonxClient()
    if not client.configured:
        print("FAIL configuration: set WATSONX_APIKEY, WATSONX_PROJECT_ID, WATSONX_URL")
        return 1
    try:
        await client._bearer_token()
        print("PASS 1 IAM token")
    except WatsonxError as exc:
        print(f"FAIL 1 IAM token: {exc.code} {exc}")
        return 1

    try:
        r = await client.chat(model_id=settings.WATSONX_REASONING_MODEL_ID,
                              messages=[{"role": "user", "content": 'Reply with JSON {"ok": true} only.'}], max_tokens=20)
        parse_vision_json(r.content)
        print(f"PASS 2 reasoning model {r.model_id} ({r.latency_seconds}s) warnings={[w['id'] for w in r.warnings]}")
    except (WatsonxError, ValueError) as exc:
        ok = False
        print(f"FAIL 2 reasoning model {settings.WATSONX_REASONING_MODEL_ID}: {getattr(exc, 'code', '')} {exc}")

    img = open(image_path, "rb").read() if image_path else _synthetic_shirt()
    out = await WatsonxVisionProvider(client=client).analyze_wardrobe_image(img)
    if out.get("analysis_available"):
        print(f"PASS 3 vision model {out['analysis_source']} ({out['analysis_latency_seconds']}s) -> "
              f"{out.get('category')} / {out.get('item_type')} / conf={out.get('confidence')}")
    else:
        ok = False
        print(f"FAIL 3 vision model {settings.WATSONX_VISION_MODEL_ID}: {out.get('reason')}")

    closet = [
        {"wardrobe_item_id": 11, "category": "Tops", "item_type": "Plaid Shirt", "title": "Blue plaid shirt", "color": "Blue",
         "pattern": "Checked", "occasions": ["Casual"], "seasonality": "Autumn"},
        {"wardrobe_item_id": 12, "category": "Bottoms", "item_type": "Chinos", "title": "Khaki chinos", "color": "Beige",
         "pattern": "Solid", "occasions": ["Casual", "Smart Casual"], "seasonality": "All-Season"},
        {"wardrobe_item_id": 13, "category": "Footwear", "item_type": "Boots", "title": "Tan leather boots", "color": "Tan",
         "pattern": "Solid", "occasions": ["Casual"], "seasonality": "Autumn"},
    ]
    ctx = {"occasion": "Casual", "time_of_day": "morning", "season": "autumn", "location": "park"}
    try:
        r = await client.chat(model_id=settings.WATSONX_REASONING_MODEL_ID, messages=[
            {"role": "system", "content": STYLIST_SYSTEM_PROMPT},
            {"role": "user", "content": build_stylist_user_message(closet, ctx)}], max_tokens=800, temperature=0.2,
            response_json=True)
        data = parse_vision_json(r.content)
        ids = [i.get("wardrobe_item_id") for i in data.get("items", [])]
        valid = all(i in (11, 12, 13) for i in ids) and ids
        print(f"{'PASS' if valid else 'FAIL'} 4 stylist round-trip ({r.latency_seconds}s) ids={ids} title={data.get('title')!r}")
        print("     reasons:", json.dumps([i.get("reason") for i in data.get("items", [])], ensure_ascii=False)[:600])
        ok = ok and bool(valid)
    except (WatsonxError, ValueError) as exc:
        ok = False
        print(f"FAIL 4 stylist round-trip: {getattr(exc, 'code', '')} {exc}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
