#!/usr/bin/env python3
"""Arabic runtime proof for the AI Stylist drawer (D-4) + engine honesty (G-08).

WHAT THIS PROVES
  1. The drawer's visible action surface AND its accessible names are Arabic in the
     Arabic UI — including the dialog's own name, which used to be the hardcoded
     English string "AI stylist" that a screen reader announced regardless of the
     interface language.
  2. A real request goes through the real API (`POST /api/v1/stylist/chat`).
  3. The reply is attributed to the engine that actually answered, and when the
     provider was unavailable the shopper is told so instead of being sold
     deterministic text as AI.
  4. The language switch works in both directions and the surface really changes.

INSTRUMENT HISTORY (kept, because a measuring tool that lies is worse than none)
  * v1 matched any URL containing "stylist" — every Vite module path — and reported
    "a real request was made" while no chat request existed.
  * v2 targeted a file input, then a form that is not a descendant of the dialog.
  * v3 selected the launcher with the Arabic word for "open", which also matched the
    IMAGE-SEARCH launcher and opened the wrong dialog.
  * v4 encoded the DEFECT in its selectors: it looked for `aria-label="AI stylist"`
    and for English chip text, so after D-4 was fixed it reported "dialog not
    present". A test that only passes while the bug exists measures the bug.
    Every visible string this script depends on is now read from ar.json.
  * v5 ran the language switch before the attribution checks; the switch reloads the
    SPA (closing the drawer and dropping the in-memory conversation), so four
    product regressions were reported that did not exist. Order is now explicit.

Usage: python3 scripts/e2e_stylist_honesty.py [--out PATH]
Exit codes: 0 pass · 1 a check failed · 3 measurement invalid · 2 instrument error
All evidence is persisted on every path.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

class Invalid(Exception):
    """A blank/unreachable render is not a pass."""


EVIDENCE: list[dict] = []
OUT = "/home/user/CONFIT_evidence/42-g08-d4-stylist-arabic-runtime.json"


def record(name: str, ok: bool, **detail) -> None:
    EVIDENCE.append({"check": name, "ok": bool(ok), **detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} " + " ".join(f"{k}={v}" for k, v in detail.items()))


def observe(name: str, **detail) -> None:
    """A measurement that is neither a requirement nor a defect. Recorded so it is
    visible in the report instead of being silently dropped."""
    EVIDENCE.append({"observation": name, **detail})
    print(f"  [OBS ] {name} " + " ".join(f"{k}={v}" for k, v in detail.items()))


def dump(verdict: str, error: str | None = None) -> None:
    payload = {"checks": EVIDENCE, "verdict": verdict}
    if error:
        payload["error"] = error
    Path(OUT).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  evidence -> {OUT}")


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    OUT = args.out
    base = args.base_url.rstrip("/")
    started = time.time()
    api_calls: list[dict] = []

    i18n_dir = Path(__file__).resolve().parents[1] / "src/i18n"
    ar = json.loads((i18n_dir / "ar.json").read_text(encoding="utf-8"))
    en = json.loads((i18n_dir / "en.json").read_text(encoding="utf-8"))
    dialog_label = ar["stylist"]["dialog_label"]
    launcher = ar["layout"]["open_ai_stylist"]
    en_dialog_label = en["stylist"]["dialog_label"]
    en_launcher = en["layout"]["open_ai_stylist"]
    dialog_sel = f'[role="dialog"][aria-label="{dialog_label}"]'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("response", lambda r: api_calls.append(
            {"method": r.request.method, "url": r.url.replace(base, ""), "status": r.status})
            if "/api/" in r.url else None)

        page.goto(base + "/", wait_until="networkidle", timeout=90000)
        page.evaluate("() => localStorage.setItem('confit_lang','ar')")
        page.reload(wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        if page.evaluate("document.documentElement.dir") != "rtl":
            raise Invalid("the document is not RTL after selecting Arabic")

        page.get_by_role("button", name=launcher, exact=True).first.click(timeout=10000)
        page.wait_for_timeout(1500)
        dialog = page.locator(dialog_sel)
        if dialog.count() == 0:
            labels = page.locator('[role="dialog"]').evaluate_all("els => els.map(e => e.getAttribute('aria-label'))")
            raise Invalid(f"the stylist dialog ({dialog_label!r}) is not present; dialogs: {labels}")

        # ── 1. localization of the surface, including accessible names ────────
        record("the dialog's accessible name is localized (a11y)",
               not re.search(r"[A-Za-z]{3}", dialog_label),
               aria_label=dialog_label)

        ALLOWED_LATIN = re.compile(r"^(CONFIT|COS|H&M|Zara|Arket|Reiss|Uniqlo|Massimo\s+Dutti)$", re.I)
        actions = dialog.locator("button, [role=button], input[type=submit]").all_inner_texts()
        latin_actions = [
            t.strip() for t in actions
            if re.search(r"[A-Za-z]{4}", t) and not re.search(r"[\u0600-\u06FF]", t)
            and not ALLOWED_LATIN.match(t.strip())
        ]
        record("every action in the drawer is Arabic in the Arabic UI", not latin_actions,
               actions_checked=len(actions), latin_actions=latin_actions[:8])

        unnamed = [i for i in range(dialog.locator("button").count())
                   if not dialog.locator("button").nth(i).get_attribute("aria-label")
                   and not (dialog.locator("button").nth(i).inner_text() or "").strip()]
        record("every drawer button has an accessible name", not unnamed, unnamed_indices=unnamed)

        rendered_ar = page.inner_text("body")
        record("the drawer's own copy is Arabic",
               ar["stylist"]["style_prompts"] in rendered_ar or ar["stylist"]["empty_title"] in rendered_ar,
               has_prompts=ar["stylist"]["style_prompts"] in rendered_ar)

        # ── every TEXT NODE inside the dialog, not just the buttons ──────────
        latin_nodes = page.evaluate("""(sel) => {
          const root = document.querySelector(sel);
          if (!root) return null;
          const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
          const latin = [], allTexts = [];
          let total = 0, n;
          while ((n = walker.nextNode())) {
            const t = (n.textContent || '').trim();
            if (!t) continue;
            total += 1;
            allTexts.push(t);
            if (/[A-Za-z]{3}/.test(t) && !/[\u0600-\u06FF]/.test(t)) latin.push(t);
          }
          return { total, latin, all: allTexts };
        }""", dialog_sel)
        if latin_nodes is None:
            raise Invalid("the drawer closed before the text sweep")
        allowed = re.compile(r"^(CONFIT|COS|H&M|Zara|Arket|Reiss|Uniqlo|Massimo\s+Dutti|AI)$", re.I)
        leaks = [t for t in latin_nodes["latin"] if not allowed.match(t)]
        # A sweep that walked nothing is INVALID, not clean: the earlier version of
        # this check reported "0 Latin nodes" from a walker that had found 0 nodes at
        # all, which would have passed on an empty dialog.
        # Validity = the walk really reached the drawer's own copy, proved by finding
        # the localized strings that the drawer is known to render. A raw node count
        # would be an arbitrary threshold; this is a positive control.
        arabic_prompt = ar["stylist"]["style_prompts"][:12]
        if not any(arabic_prompt in t for t in latin_nodes["all"]):
            raise Invalid(f"the text sweep did not reach the drawer's own copy "
                          f"(walked {latin_nodes['total']} nodes, wanted {arabic_prompt!r})")
        record("no untranslated English text node remains in the Arabic drawer",
               not leaks, text_nodes_walked=latin_nodes["total"], leaks=leaks[:10])

        # ── 2. a real request through the real API ───────────────────────────
        chip_label = ar["stylist"]["occasion_work"]
        chip = dialog.locator("button").filter(has_text=chip_label).first
        if chip.count() == 0:
            raise Invalid(f"the quick-start chip {chip_label!r} is not rendered")
        chip.click(force=True, timeout=10000)
        page.wait_for_timeout(9000)

        posts = [c for c in api_calls if c["method"] == "POST" and "stylist/chat" in c["url"]]
        record("the browser made a real POST /api/v1/stylist/chat", len(posts) >= 1 and posts[0]["status"] == 200,
               calls=posts[:2])

        bubbles = page.locator("[data-engine]")
        engine_attr = bubbles.first.get_attribute("data-engine") if bubbles.count() else None
        label_text = bubbles.first.inner_text() if bubbles.count() else ""
        record("the reply is labelled with the engine that actually answered",
               bool(engine_attr), data_engine=engine_attr)

        fallback_marker = "مزوّد الذكاء الاصطناعي غير متاح"
        if engine_attr and "Grounded Styling Engine" in str(engine_attr):
            record("the Arabic label states the AI provider was unavailable",
                   fallback_marker in label_text, label=label_text[:110])
        else:
            record("a provider answer is attributed to that provider", "Answered by" in label_text or "تمّت الإجابة" in label_text,
                   label=label_text[:110], note="a provider answered in this run; the fallback path is covered by the unit tests")

        record("no unconditional AI claim accompanies this reply",
               not re.search(r"(AI Stylist|الستايلست الذكي)", label_text or ""),
               label=label_text[:80])

        # ── 2b. the ERROR state ──────────────────────────────────────────────
        # Why this section exists: the first version of this instrument only ever
        # saw the happy path. `Styling…` (loading) and `Retry` (error) sat in the
        # drawer as English literals, and the sweep reported a clean drawer because
        # neither state was on screen. A measurement that only visits the success
        # path cannot say a surface is localized. The API is failed ON PURPOSE here.
        page.route("**/api/v1/stylist/chat", lambda route: route.fulfill(
            status=500, content_type="application/json",
            body=json.dumps({"detail": "injected failure: error-state localization sweep"})))

        box = dialog.locator("input[type=text]").first
        box.fill("أريد إطلالة للعمل")
        box.press("Enter")
        page.wait_for_timeout(3500)

        # Two different questions, measured separately:
        #   chrome  — the drawer's own furniture (error box, retry, input, chips)
        #   content — the answer card (generated prose + catalogue data)
        # Mixing them reported the answer's English product titles as if they were
        # untranslated interface copy, which is a different (and real) finding.
        err_nodes = page.evaluate("""(sel) => {
          const root = document.querySelector(sel);
          if (!root) return null;
          const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
          const chrome = [], content = [];
          let n;
          while ((n = w.nextNode())) {
            const t = (n.textContent || '').trim();
            if (!t) continue;
            let p = n.parentElement, inAnswer = false;
            while (p && p !== root) {
              if (p.hasAttribute && (p.hasAttribute('data-engine') || p.hasAttribute('data-answer') || p.hasAttribute('data-conversation'))) { inAnswer = true; break; }
              p = p.parentElement;
            }
            (inAnswer ? content : chrome).push(t);
          }
          return { chrome, content };
        }""", dialog_sel)
        if err_nodes is None:
            raise Invalid("the drawer closed before the error-state sweep")
        allowed = re.compile(r"^(CONFIT|COS|H&M|Zara|Arket|Reiss|Uniqlo|Massimo\s+Dutti)$", re.I)
        def latin_only(texts):
            return [t for t in texts
                    if re.search(r"[A-Za-z]{3}", t) and not re.search(r"[\u0600-\u06FF]", t)
                    and not allowed.match(t)]
        chrome_leaks = latin_only(err_nodes["chrome"])
        content_leaks = latin_only(err_nodes["content"])
        record("the error state renders an Arabic action (Retry)",
               ar["stylist"]["retry"] in err_nodes["chrome"],
               retry_label_present=ar["stylist"]["retry"] in err_nodes["chrome"])
        record("the error state's own chrome is Arabic (no transport string, no status code)",
               not chrome_leaks and not any(re.search(r"\b(4|5)\d\d\b", t) for t in err_nodes["chrome"]),
               chrome_nodes=len(err_nodes["chrome"]), leaks=chrome_leaks[:6])
        observe("the answer card still renders English content in the Arabic UI",
                english_content_nodes=len(content_leaks),
                sample=content_leaks[:4],
                note="catalogue data (product titles, category names) is legitimately English — it is "
                     "the same value the API and database hold. The generated PROSE in the same card "
                     "is not: it is produced by the deterministic engine in English. Recorded as an "
                     "open finding; D-4 covers the drawer's own copy, not the answer body.")

        page.unroute("**/api/v1/stylist/chat")

        # ── 3. language switch, both directions ──────────────────────────────
        # The SPA reloads on a language switch, which closes the drawer; each side of
        # the switch is therefore reopened before it is judged.
        # The switcher renders each language's name in that language
        # (`languageDisplayName(code)` with no uiLang): "English" / "العربية".
        #
        # It lives in the header, BEHIND the drawer's modal backdrop — a pointer user
        # with the drawer open cannot reach it at all (Playwright says the backdrop
        # "intercepts pointer events"). The realistic journey therefore closes the
        # drawer with the keyboard first, and that Escape itself is checked, because
        # "a modal must be closable without a mouse" is an accessibility requirement.
        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        record("Escape closes the drawer (keyboard accessibility)",
               page.locator(dialog_sel).count() == 0)
        bubbles_before_switch = page.locator("[data-engine]").count()

        page.evaluate("() => { window.__confit_marker = 'kept'; }")

        def switch(button_label: str) -> str:
            """Click the real switcher. Returns 'soft' if the SPA kept running."""
            page.get_by_role("button", name=button_label, exact=True).first.click(timeout=8000)
            page.wait_for_timeout(2500)
            survived = page.evaluate("() => window.__confit_marker")
            return "soft (no reload)" if survived == "kept" else "hard reload"

        kind = switch("English")
        page.get_by_role("button", name=en_launcher, exact=True).first.click(timeout=10000)
        page.wait_for_timeout(1600)
        en_ui = page.inner_text("body")        # AFTER the drawer is open, not before
        en_dialog = page.locator(f'[role="dialog"][aria-label="{en_dialog_label}"]')
        # `inner_text` returns text as RENDERED, so a `uppercase` class turns
        # "Style Prompts:" into "STYLE PROMPTS:" — compare case-insensitively.
        record("switching to English renders the English drawer surface",
               en_dialog.count() > 0 and en["stylist"]["style_prompts"].lower() in en_ui.lower(),
               switch=kind, dialog_present=en_dialog.count() > 0,
               prompts_present=en["stylist"]["style_prompts"] in en_ui,
               aria_label=en_dialog.first.get_attribute("aria-label") if en_dialog.count() else None,
               drawer_text=(en_dialog.first.inner_text()[:260].replace("\n", " | ")
                            if en_dialog.count() else None))

        # LIVENESS CONTROL for the sweep above. A detector that reports "no English
        # leaked" is only evidence if the same code sees English when it is there.
        # The identical walker runs against the ENGLISH drawer, where Latin text is
        # expected: if it finds none, the AR sweep is blind and must be INVALID.
        en_sweep = page.evaluate("""(sel) => {
          const root = document.querySelector(sel);
          if (!root) return null;
          const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
          const latin = []; let total = 0, n;
          while ((n = walker.nextNode())) {
            const t = (n.textContent || '').trim();
            if (!t) continue;
            total += 1;
            if (/[A-Za-z]{3}/.test(t) && !/[\u0600-\u06FF]/.test(t)) latin.push(t);
          }
          return { total, latin };
        }""", f'[role="dialog"][aria-label="{en_dialog_label}"]')
        if en_sweep is None or len(en_sweep["latin"]) < 5:
            raise Invalid(f"the text sweep is blind: it found {en_sweep and len(en_sweep['latin'])} "
                          "Latin nodes in the ENGLISH drawer, so a clean Arabic result means nothing")
        record("the text sweep is live (positive control in the English drawer)",
               len(en_sweep["latin"]) >= 5,
               latin_nodes_seen=len(en_sweep["latin"]), sample=en_sweep["latin"][:3])

        page.keyboard.press("Escape")
        page.wait_for_timeout(900)
        kind_back = switch("العربية")
        page.get_by_role("button", name=launcher, exact=True).first.click(timeout=10000)
        page.wait_for_timeout(1600)
        ar_again = page.inner_text("body")
        record("switching back to Arabic restores the Arabic drawer surface",
               page.locator(dialog_sel).count() > 0 and ar["stylist"]["style_prompts"] in ar_again,
               switch=kind_back, prompts_present=ar["stylist"]["style_prompts"] in ar_again)

        observe("conversation state across a language switch",
                bubbles_before_switch=bubbles_before_switch,
                bubbles_after=page.locator("[data-engine]").count(),
                note="the drawer holds the conversation in component state; the brief does not "
                     "require it to survive closing the drawer, so this is recorded, not judged")

        browser.close()

    elapsed = round(time.time() - started, 1)
    failed = [c for c in EVIDENCE if "ok" in c and not c["ok"]]
    payload = {"checks": EVIDENCE, "duration_seconds": elapsed, "api_calls": len(api_calls),
               "verdict": "PASS" if not failed else f"FAIL ({len(failed)} check(s))"}
    Path(OUT).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    judged = [c for c in EVIDENCE if "ok" in c]
    print(f"\n  {sum(1 for c in judged if c['ok'])}/{len(judged)} checks passed | {elapsed}s")
    print(f"  evidence -> {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Invalid as exc:
        print(f"\n  MEASUREMENT INVALID: {exc}")
        dump("INVALID: measurement not trustworthy", str(exc))
        sys.exit(3)
    except Exception as exc:                                  # never lose evidence
        import traceback
        traceback.print_exc()
        dump("ERROR: instrument failure, partial evidence kept", f"{type(exc).__name__}: {exc}")
        sys.exit(2)
