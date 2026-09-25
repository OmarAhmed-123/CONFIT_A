#!/usr/bin/env python3
"""G-08 runtime proof: what a shopper is TOLD when no AI provider answered.

The API returns an `engine` label; this drives the real UI in Arabic and reads what
is rendered, because "the API is honest" and "the shopper is told the truth" are
different claims. A bubble that says "AI Stylist" over deterministic text is the
defect; an honest label is only real if it reaches the screen.

State under test: the local stack is configured with a real provider key whose
call FAILED at the provider (measured: OpenAI 429, Gemini 503), so the deterministic
engine answered. That is the case that must not be labelled as AI.

Usage: python3 scripts/e2e_stylist_honesty.py [--base-url URL] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROMPT = "I need a smart casual outfit for an art gallery opening under $300"
EVIDENCE: list[dict] = []


class Invalid(Exception):
    """A blank or unreachable render is not a pass."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/home/user/CONFIT_evidence/38-g08-stylist-honesty-runtime.json")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    started = time.time()
    network: list[dict] = []

    def record(name: str, ok: bool, **detail):
        EVIDENCE.append({"check": name, "ok": bool(ok), **detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} " + " ".join(f"{k}={v}" for k, v in detail.items()))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        # Only real API traffic counts. The first version of this filter matched any
        # URL containing "stylist" — which is every Vite module path — so it reported
        # "a real request was made" while no chat request existed.
        page.on("response", lambda r: network.append(
            {"method": r.request.method, "url": r.url.replace(base, ""), "status": r.status})
            if "/api/" in r.url else None)

        page.goto(base + "/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(800)

        # Arabic UI, set directly so the state is deterministic (clicking the switch
        # left a menu open that swallowed the next click).
        page.evaluate("() => localStorage.setItem('confit_lang','ar')")
        page.goto(base + "/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1500)

        # The launcher's accessible name comes from ar.json, not from a guess:
        # matching on the Arabic word for "open" also selected the IMAGE-SEARCH
        # launcher ("افتح البحث بالصورة"), which opened the wrong dialog.
        ar = json.loads((Path(__file__).resolve().parents[1] / "src/i18n/ar.json").read_text(encoding="utf-8"))
        launcher = ar["layout"]["open_ai_stylist"]
        try:
            page.get_by_role("button", name=launcher, exact=True).first.click(timeout=8000)
        except Exception as exc:
            raise Invalid(f"the stylist launcher {launcher!r} could not be clicked: {type(exc).__name__}")
        page.wait_for_timeout(1500)

        body = page.inner_text("body")
        if len(body) < 400:
            raise Invalid(f"stylist screen rendered only {len(body)} chars — cannot judge the label")
        dir_attr = page.evaluate("document.documentElement.dir")
        record("the drawer opens from a localized launcher in the Arabic UI", dir_attr == "rtl" and len(body) > 400,
               dir=dir_attr, chars=len(body))

        # type a real request in the drawer's own field (Arabic placeholder)
        # Several dialogs can exist in the DOM (a visual-search modal too), so the
        # stylist drawer is identified by its own aria-label — which is also the
        # hardcoded-English defect being measured below.
        dialog = page.locator('[role="dialog"][aria-label="AI stylist"]')
        if dialog.count() == 0:
            labels = page.locator('[role="dialog"]').evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")
            raise Invalid(f"the stylist dialog is not present; dialogs found: {labels}")
        # Send the request the way a shopper does: one of the drawer's own
        # quick-start prompts. (Typing into the field was abandoned after three
        # instrument defects: a file input sat first in the DOM, the form is not a
        # descendant of the dialog, and a decorative overlay intercepts pointer
        # events. The chip is a real user path and exercises the same endpoint.)
        chip = dialog.locator("button").filter(
            has_text=re.compile(r"wedding|silk|Champagne|dinner", re.I)).first
        chip.click(force=True, timeout=10000)
        page.wait_for_timeout(9000)

        # ── two i18n defects visible in the ARABIC ui, recorded as measurements so
        #    the report can cite exact strings rather than impressions
        dialog_label = dialog.first.get_attribute("aria-label")
        record("the dialog's accessible name is localized (a11y)",
               dialog_label != "AI stylist", aria_label=dialog_label,
               note="hardcoded English accessible name; a screen-reader user in Arabic "
                    "hears 'AI stylist' regardless of the engine that answered")
        chips = dialog.locator("button").all_inner_texts()
        english_chips = [c for c in chips if re.search(r"[A-Za-z]{3}", c) and not re.search(r"[\u0600-\u06FF]", c)]
        record("quick-start chips and the submit label are Arabic in the Arabic UI",
               not english_chips, english_strings_in_arabic_ui=english_chips[:8])

        rendered = page.inner_text("body")
        bubble_engine = page.locator("[data-engine]")
        engine_attr = bubble_engine.first.get_attribute("data-engine") if bubble_engine.count() else None
        label_text = bubble_engine.first.inner_text() if bubble_engine.count() else ""

        api_calls = [n for n in network if n["method"] == "POST" and "stylist" in n["url"]]
        record("the browser made a real POST /stylist/chat request", len(api_calls) >= 1,
               calls=api_calls[:3])

        arabic_fallback_label = "مزوّد الذكاء الاصطناعي غير متاح"
        honest = bool(engine_attr) and "Grounded Styling Engine" in str(engine_attr)
        record("the reply is labelled with the engine that actually answered", honest,
               data_engine=engine_attr)

        record("the Arabic label states the AI provider was unavailable", arabic_fallback_label in label_text,
               label=label_text[:120])

        # The defect being guarded: calling deterministic text an AI answer.
        ai_claims = re.findall(r"(AI Stylist|الستايلست الذكي|مدعوم بالذكاء الاصطناعي)", rendered)
        record("no unconditional AI claim is rendered next to a fallback answer",
               len(ai_claims) == 0, hits=ai_claims[:5],
               note="the words may exist elsewhere on the page; the check is that the "
                    "reply's own attribution is not an AI claim")

        # a failed provider must be visible to the shopper, not silent
        record("the provider failure is disclosed rather than hidden",
               arabic_fallback_label in rendered)

        # The screenshot is an artifact, not a measurement: a renderer crash while
        # taking it once destroyed an entire otherwise-complete run's evidence.
        try:
            page.screenshot(path=str(Path(args.out).with_suffix(".png")), full_page=True)
        except Exception as exc:
            record("screenshot captured (artifact only)", False, error=type(exc).__name__)
            EVIDENCE.pop() if EVIDENCE and EVIDENCE[-1]["check"].startswith("screenshot") else None
            print(f"  ..  screenshot skipped: {type(exc).__name__}")
        browser.close()

    payload = {"checks": EVIDENCE, "duration_seconds": round(time.time() - started, 1),
               "verdict": "PASS" if all(c["ok"] for c in EVIDENCE) else "FAIL"}
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  verdict: {payload['verdict']} -> {args.out}")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    _out = "/home/user/CONFIT_evidence/38-g08-stylist-honesty-runtime.json"
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            _out = sys.argv[i + 1]
    try:
        sys.exit(main())
    except Invalid as exc:
        print(f"\n  MEASUREMENT INVALID: {exc}")
        Path(_out).write_text(json.dumps({"checks": EVIDENCE, "verdict": "INVALID", "error": str(exc)},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(3)
    except Exception as exc:                      # no measurement may be lost
        import traceback
        traceback.print_exc()
        Path(_out).write_text(json.dumps(
            {"checks": EVIDENCE, "verdict": "ERROR: instrument failure, partial evidence kept",
             "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(2)
