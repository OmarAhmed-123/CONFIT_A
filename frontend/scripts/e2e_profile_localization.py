#!/usr/bin/env python3
"""Profile localization runtime proof — Arabic UI, English stored tokens.

WHAT THIS PROVES THAT UNIT TESTS CANNOT
---------------------------------------
`profileTokenLabels.test.ts` asserts the contract statically (labels Arabic, values
English). This drives the real stack and closes the loop the mission asks for:

    Arabic UI  ->  stable internal value  ->  API  ->  backend  ->  DB  ->  UI

1. An account is created locally (never production), the UI is switched to Arabic,
   and the 5-step style wizard is answered in Arabic.
2. Tapping the Arabic chip for "Old Money" must SAVE the English token — checked by
   reading the profile back from the API, not by trusting the screen.
3. The profile card must then render the ARABIC label while the API still returns
   the English token (label and value are different layers, verified in one run).
4. HONESTY: saving a profile without body measurements must NOT render "178 cm",
   "72 kg" or a default silhouette. The old card fabricated all three.
5. Numbers/currency must use the Arabic locale when the UI is Arabic.

RUN VALIDITY (same contract as e2e_consumer_journey.py): a blank/short render or an
API that does not answer is MEASUREMENT INVALID (exit 3), never a pass. Evidence is
written even when a step fails.

Usage:
    python3 scripts/e2e_profile_localization.py [--base-url URL] [--out PATH] [--headed]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

MIN_RENDERED_TEXT = 800
EV = None


class Invalid(Exception):
    """The measurement itself is not trustworthy — never treated as a pass."""


class Evidence:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.network: list[dict] = []
        self.console_errors: list[str] = []

    def step(self, name: str, ok: bool, **detail) -> None:
        self.steps.append({"step": name, "ok": bool(ok), **detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} " +
              " ".join(f"{k}={v}" for k, v in detail.items()))
        if not ok:
            raise AssertionError(f"step failed: {name} | {detail}")


def attach(page: Page, ev: Evidence, base: str) -> None:
    page.on("response", lambda r: ev.network.append(
        {"method": r.request.method, "url": r.url.replace(base, ""), "status": r.status})
        if "/api/" in r.url else None)
    page.on("console", lambda m: ev.console_errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: ev.console_errors.append(f"pageerror: {e}"))


def rendered_text(page: Page) -> str:
    try:
        return page.inner_text("body")
    except Exception:
        raise Invalid("could not read the rendered body text")


def assert_renderable(page: Page, where: str, minimum: int = MIN_RENDERED_TEXT) -> str:
    text = rendered_text(page)
    if len(text) < minimum:
        raise Invalid(f"{where}: only {len(text)} chars rendered (min {minimum}). starts: {text[:160]!r}")
    return text


def switch_language(page: Page, lang: str, base: str) -> None:
    try:
        label = "العربية" if lang == "ar" else "English"
        page.get_by_role("button", name=label, exact=True).first.click(timeout=4000)
        page.wait_for_timeout(1200)
    except Exception:
        page.evaluate("(l) => localStorage.setItem('confit_lang', l)", lang)
        page.reload(wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1200)


def main() -> int:
    global EV
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/tmp/e2e_profile_localization.json")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    ev = Evidence()
    EV = ev
    started = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        attach(page, ev, base)

        page.goto(base + "/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1200)

        # ── create a LOCAL account through the app's own API (cookies land in
        #    this browser context). Local stack only; nothing touches production.
        email = f"e2e-profile-{uuid.uuid4().hex[:10]}@example.com"
        created = page.evaluate(
            """async (email) => {
                 const r = await fetch('/api/v1/auth/register', {
                   method: 'POST', headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({email, password: 'E2eProfile!2345',
                                         full_name: 'E2E Profile', preferred_language: 'ar'}),
                 });
                 return {status: r.status, body: (await r.text()).slice(0, 200)};
               }""", email)
        if created["status"] not in (200, 201):
            raise Invalid(f"could not create the probe account: {created}")
        ev.step("probe account created on the local stack", True, status=created["status"])

        # ── Arabic UI, wizard forced open by the app's own query contract
        switch_language(page, "ar", base)
        page.goto(base + "/profile?onboarding=1", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        text_ar = assert_renderable(page, "profile-ar")
        dir_ar = page.evaluate("document.documentElement.dir")
        ev.step("profile view renders in Arabic RTL", dir_ar == "rtl", dir=dir_ar, chars=len(text_ar))

        wizard_open = "معالج ملف الستايل" in text_ar
        ev.step("the style wizard auto-opens from onboarding=1", wizard_open)

        # ── step 1: the Arabic label must be visible AND the token must be the
        #    one stored. "الأناقة الراقية التقليدية" is the Arabic label for the
        #    English token "Old Money".
        arabic_label = "الأناقة الراقية التقليدية"
        arabic_visible = arabic_label in rendered_text(page)
        english_visible = "Old Money" in rendered_text(page)
        ev.step("wizard step 1 shows Arabic archetype labels, not English tokens",
                arabic_visible and not english_visible,
                arabic_label_present=arabic_visible, english_token_visible=english_visible)

        page.get_by_role("button", name=arabic_label, exact=True).first.click(timeout=8000)
        page.wait_for_timeout(400)

        # Walk the wizard to the last step WITHOUT entering body measurements.
        # On step 4 a budget is set deliberately: the earlier version of this
        # script asserted "Arabic digits are used" while nothing numeric was on
        # screen (0 digits found), i.e. it passed without measuring anything.
        for step_index in range(4):
            page.get_by_role("button", name=re.compile("الخطوة التالية")).first.click(timeout=8000)
            page.wait_for_timeout(700)
            if step_index == 2:   # now on step 4 (budget & occasions)
                set_ok = page.evaluate(
                    """() => {
                         const inputs = [...document.querySelectorAll('input[type=range]')];
                         if (inputs.length < 3) return false;
                         const setter = Object.getOwnPropertyDescriptor(
                           window.HTMLInputElement.prototype, 'value').set;
                         const values = [400, 1500, 450];
                         inputs.slice(0, 3).forEach((el, i) => {
                           setter.call(el, String(values[i]));
                           el.dispatchEvent(new Event('input', {bubbles: true}));
                         });
                         return true;
                       }""")
                page.wait_for_timeout(400)
                if not set_ok:
                    raise Invalid("budget sliders not found on step 4 — cannot measure number formatting")
        page.get_by_role("button", name=re.compile("إنهاء وحفظ الملف")).first.click(timeout=8000)
        page.wait_for_timeout(2500)

        # ── the API is the source of truth for what was STORED
        stored = page.evaluate(
            """async () => {
                 const r = await fetch('/api/v1/profile/me', {headers: {'Accept': 'application/json'}});
                 return {status: r.status, body: await r.json()};
               }""")
        if stored["status"] != 200 or not isinstance(stored["body"], dict):
            raise Invalid(f"profile read-back failed: {stored['status']} {str(stored['body'])[:160]}")
        archetypes = stored["body"].get("style_archetypes") or []
        ev.step("the Arabic chip SAVED the English token through the API",
                archetypes == ["Old Money"], stored_archetypes=archetypes)

        body_attrs = stored["body"].get("body_attributes")
        ev.step("no body measurements were fabricated by skipping the step",
                not body_attrs, stored_body_attributes=body_attrs)

        # ── the card must show the Arabic LABEL for that stored English token
        page.goto(base + "/profile", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        card_ar = assert_renderable(page, "profile-card-ar")
        ev.step("the card renders the Arabic label for the stored English token",
                arabic_label in card_ar and "Old Money" not in card_ar)

        # ── HONESTY: the old card printed 178 cm / 72 kg / Athletic for a
        #    profile with no measurements at all.
        fabricated = [s for s in ("178", "72", "Athletic", "رياضي") if re.search(rf"(^|\s){s}(\s|$)", card_ar)]
        not_set_ar = "غير محدّد"
        ev.step("no fabricated body values are rendered",
                not fabricated and not_set_ar in card_ar,
                fabricated_hits=fabricated, not_set_present=not_set_ar in card_ar)

        # ── numbers must follow the Arabic locale when the page is Arabic.
        #    A budget was entered above, so this is a real measurement now.
        arabic_digits = re.findall(r"[\u0660-\u0669]", card_ar)
        latin_money = re.findall(r"\$\s?\d", card_ar)
        ev.step("money renders with Arabic-Indic digits and no bare '$'",
                len(arabic_digits) > 0 and not latin_money,
                arabic_digits=len(arabic_digits), latin_dollar_hits=len(latin_money))

        # ── switching back to English must restore the English facing label while
        #    the stored token is unchanged (no data mutation from a UI switch)
        switch_language(page, "en", base)
        page.goto(base + "/profile", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1800)
        card_en = assert_renderable(page, "profile-card-en")
        stored_again = page.evaluate(
            """async () => (await (await fetch('/api/v1/profile/me')).json()).style_archetypes""")
        ev.step("English UI shows the English label and the token never changed",
                "Old Money" in card_en and stored_again == ["Old Money"],
                stored_after_switch=stored_again)

        page.screenshot(path=str(Path(args.out).with_suffix(".ar.png")), full_page=True)
        browser.close()

    server_errors = [n for n in ev.network if n["status"] >= 500]
    payload = {
        "base_url": base, "duration_seconds": round(time.time() - started, 1),
        "steps": ev.steps, "api_calls": len(ev.network),
        "server_errors": server_errors, "console_errors": ev.console_errors[:10],
        "verdict": "PASS" if not server_errors else "FAIL: backend 5xx during run",
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  api calls: {len(ev.network)} | 5xx: {len(server_errors)} | console errors: {len(ev.console_errors)}")
    print(f"  evidence -> {args.out}")
    return 1 if server_errors else 0


def _dump(out: str, verdict: str, error: str | None = None) -> None:
    if EV is None:
        return
    payload = {"steps": EV.steps, "api_calls": len(EV.network),
               "server_errors": [n for n in EV.network if n["status"] >= 500],
               "console_errors": EV.console_errors[:10], "verdict": verdict}
    if error:
        payload["error"] = error
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  partial evidence -> {out}")


if __name__ == "__main__":
    _out = "/tmp/e2e_profile_localization.json"
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            _out = sys.argv[i + 1]
    try:
        sys.exit(main())
    except Invalid as exc:
        print(f"\n  MEASUREMENT INVALID — no verdict: {exc}")
        _dump(_out, "INVALID: measurement not trustworthy", str(exc))
        sys.exit(3)
    except AssertionError as exc:
        print(f"\n  FAIL: {exc}")
        _dump(_out, "FAIL: a step failed", str(exc))
        sys.exit(1)
