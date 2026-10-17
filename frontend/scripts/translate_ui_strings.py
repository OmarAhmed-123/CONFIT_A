#!/usr/bin/env python3
"""
Batch-translate CONFIT UI strings EN -> AR with the translation-dedicated
NVIDIA credential, then verify the result.

    NVIDIA_API_KEY_RIVA_TRANSLATE=nvapi-…  python3 scripts/translate_ui_strings.py \
        strings.json  >  translated.json

`strings.json` is a list of {"ns": …, "key": …, "en": …}.

WHY THE PROMPT LOOKS LIKE THIS
------------------------------
`nvidia/riva-translate-4b-instruct-v2` is instruction-blind: the provider
registry (backend/app/providers/nvidia/registry.py, ModelRole.TRANSLATION)
records that it ignores the system turn. Measured again on 2026-10-17 while
extracting the hard-coded English from seven screens:

  * With the instruction in the SYSTEM turn, 6 of 9 short EN->AR strings came
    back in the wrong language - French ("Eliminer"), Norwegian
    ("Arbeidsbekledning"), Ukrainian, Czech. Not merely unidiomatic: unusable.
  * With the instruction folded into the USER turn, 12 of 12 came back as
    clean Arabic.

So the instruction lives in the user turn. Keep it to ONE sentence: when a
multi-sentence rule block was used, the model translated the rule block and
returned it as the answer ("قواعد: احتفظ بكل رمز مكتوب ك…" instead of the
string). G8 below rejects that class of output.

WHAT THIS SCRIPT CANNOT DO FOR YOU
----------------------------------
It cannot tell a correct translation from a fluent wrong one. On the
2026-10-17 run of 126 strings, 67 (53%) needed a reviewer correction, and the
corrections were not cosmetic:

    EN                          riva first draft            correct
    Unlocks +N New Outfits      أزِل +N …  ("Remove!")      يُتيح لك +N …
    Conversion Funnel           …القالب ("the template")    قمع التحويل
    Trending Placements         …التقنيات المتطورة          المواضع … والأكثر رواجًا
    failed orders               المفلسة ("bankrupt")        الفاشلة
    styling what you own        تزيين ("decorating")        تنسيق
    Size (garment)              الحجم                       المقاس
    return-marked line          العلامات المرسومة           بنود … كمرتجع
    are not established by      = asserts they are NOT      = not established
      this screen                 reset (inverts a
                                  disclaimer)

Every string therefore needs a human pass. The guards below only catch the
mechanical failures; they pass a fluent mistranslation without complaint.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

BASE = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/riva-translate-4b-instruct-v2"

# One sentence, in the USER turn. See the module docstring.
TPL_FWD = (
    "Translate the following English user-interface text into Arabic. "
    "Reply with the Arabic translation only.\nEnglish: {}\nArabic:"
)
TPL_BACK = (
    "Translate the following Arabic text into English. "
    "Reply with the English translation only.\nArabic: {}\nEnglish:"
)

# Latin that is CORRECT to keep verbatim in an Arabic CONFIT UI.
KEEP = re.compile(
    r"CONFIT|VTON|AI|BOPIS|SKU|PDF|CSV|MFA|2FA|ROAS|CPC|RTL|LTR|EN|AR|GDPR|ID"
    r"|JPEG|PNG|WebP|MB|GB|cm|in|lbs|kg|px"
    r"|StoreLocation|StoreInventory|RecentlyViewed|TryOnSession|CartItem|OrderItem"
    r"|SponsoredPlacement|impressions|clicks|Virtual|Stylist|Canvas|Builder|Ensemble"
    r"|\d|[%°]|\+",
    re.I,
)

# If the model echoed our own instructions back as Arabic, it never translated
# the string. Two or more of these together is an echo, not vocabulary.
ECHO = ["قواعد", "احتفظ", "بالضبط", "كما هو", "رمز مكتوب", "علامات اقتباس"]

ARABIC = re.compile(r"[؀-ۿ]")


def call(text: str, key: str, tpl: str = TPL_FWD, retries: int = 3) -> str:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": tpl.format(text)}],
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    req = urllib.request.Request(
        BASE,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    last: Exception | None = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # network layer; retried below
            last = exc
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"translate failed for {text!r}: {last}")


def clean(s: str) -> str:
    for _ in range(2):
        s = re.sub(
            r"^(translation|الترجمة|arabic|العربية|english|الإنجليزية)\s*[:\-]\s*",
            "",
            s.strip(),
            flags=re.I,
        )
    return s.strip().strip('"').strip("'").strip()


def guard(en: str, ar: str) -> list[str]:
    """Mechanical checks only. A fluent mistranslation passes all of them."""
    bad: list[str] = []
    body = re.sub(r"\{\{\w+\}\}", "", ar)  # placeholders are not leakage
    if not ARABIC.search(ar):
        bad.append("G1-no-arabic")
    if ar.strip() == en.strip() and not re.fullmatch(r"[A-Z]{3,}:?", ar.strip()):
        bad.append("G5-unchanged")
    for w in re.findall(r"[A-Za-z]{3,}", body):
        if not KEEP.fullmatch(w):
            bad.append(f"G2-latin:{w}")
    for p in re.findall(r"\{\{\w+\}\}", en):
        if p not in ar:
            bad.append(f"G3-lost:{p}")
    if sum(e in ar for e in ECHO) >= 2:
        bad.append("G8-echo-instruction")
    if len(en.split()) >= 8 and len(ar.split()) < len(en.split()) * 0.45:
        bad.append("G6-truncated")
    if len(ar) < max(2, len(en) * 0.3):
        bad.append("G6-short")
    return sorted(set(bad))


def main() -> int:
    key = os.environ.get("NVIDIA_API_KEY_RIVA_TRANSLATE")
    if not key:
        print("NVIDIA_API_KEY_RIVA_TRANSLATE is not set", file=sys.stderr)
        return 2
    items = json.load(open(sys.argv[1], encoding="utf-8"))
    out = []
    for i, it in enumerate(items, 1):
        en = it["en"]
        ar, bad = "", ["G0"]
        for _ in range(4):  # resample: temperature 0 but the failure is not thermal
            ar = clean(call(en, key))
            bad = guard(en, ar)
            if not bad:
                break
            time.sleep(1.2)
        it = {**it, "ar": ar, "bad": bad,
              "roundtrip": None if bad else clean(call(ar, key, TPL_BACK))}
        out.append(it)
        print(f"[{i}/{len(items)}] {'OK ' if not bad else 'BAD'} "
              f"{it['ns']}.{it['key']}  {ar[:60]}", file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print(f"\n{sum(1 for o in out if not o['bad'])}/{len(out)} passed the guard. "
          f"ALL strings still need a human review pass — see the module docstring.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
