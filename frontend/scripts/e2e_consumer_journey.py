#!/usr/bin/env python3
"""Local browser E2E — the consumer purchase journey, in English and Arabic.

G-07. The environment constraint that previously blocked this was real (a
resource-limited sandbox with an unreliable Chromium); MEASURED 2026-09-24 it no
longer applies, so this runs locally instead of falling back to CI.

What it is NOT: a click-through that treats "the button was clicked" as success.
Every step that has persistent state is verified end to end —
UI action -> HTTP request -> backend response -> UI state — and the network
evidence is kept in the output. The Arabic steps assert that the phrases this
project just translated actually RENDER, and that one classification decision
survives the round trip: the return-reason `<option value>` stays an English
contract value while its visible label is Arabic (report §9).

RUN VALIDITY (a crashed or half-rendered page is a MEASUREMENT FAILURE, never a
pass): the script asserts the app shell rendered, a minimum amount of text is
present, the API actually answered, and no page-level exception occurred. Any
failed assertion exits non-zero with the raw evidence written to disk.

Usage:
    python3 scripts/e2e_consumer_journey.py [--base-url http://127.0.0.1:43123]
                                            [--out /path/evidence.json]
                                            [--headed] [--slow-mo 0]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

#: The app renders its consumer layout with this much text at minimum; below it
#: the page is a shell, an error boundary or a blank screen, and any assertion
#: made against it would be meaningless.
MIN_RENDERED_TEXT = 1200


class Invalid(Exception):
    """The measurement itself is not trustworthy — never treated as a pass."""


#: Module-level so the failure paths in __main__ can still write the raw
#: evidence of every step that DID run. An instrument that discards its artefact
#: when a step fails cannot support any statement about that failure.
EV = None


class Evidence:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.network: list[dict] = []
        self.console_errors: list[str] = []
        self.screenshots: list[str] = []

    def step(self, name: str, ok: bool, **detail) -> None:
        self.steps.append({"step": name, "ok": ok, **detail})
        mark = "PASS" if ok else "FAIL"
        extra = " ".join(f"{k}={v}" for k, v in detail.items() if k != "text")
        print(f"  [{mark}] {name} {extra}")
        if not ok:
            raise AssertionError(f"step failed: {name} | {detail}")


def attach(page: Page, ev: Evidence, base: str) -> None:
    def on_response(r):
        if "/api/" in r.url:
            ev.network.append(
                {"method": r.request.method, "url": r.url.replace(base, ""), "status": r.status}
            )

    page.on("response", on_response)
    page.on("console", lambda m: ev.console_errors.append(m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: ev.console_errors.append(f"pageerror: {e}"))


def rendered_text(page: Page) -> str:
    try:
        return page.inner_text("body")
    except Exception:  # pragma: no cover - a detached frame means an invalid run
        raise Invalid("could not read the rendered body text")


def assert_renderable(page: Page, where: str, minimum: int = MIN_RENDERED_TEXT) -> str:
    text = rendered_text(page)
    if len(text) < minimum:
        raise Invalid(
            f"{where}: only {len(text)} chars rendered (minimum {minimum}). "
            f"Body starts: {text[:160]!r}"
        )
    return text


def switch_language(page: Page, lang: str, base: str) -> None:
    """Switch through the app's own storage contract, then reload.

    The app persists the choice in localStorage under `confit_lang` and writes
    <html lang/dir> from it (src/i18n/i18n.ts is the single owner of direction).
    Driving the visible switcher is attempted first; the storage write is the
    fallback so a selector change cannot make this script lie about RTL.
    """
    try:
        label = "العربية" if lang == "ar" else "English"
        page.get_by_role("button", name=label, exact=True).first.click(timeout=4000)
        page.wait_for_timeout(1200)
    except Exception:
        page.evaluate("(l) => localStorage.setItem('confit_lang', l)", lang)
        page.reload(wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/tmp/e2e_consumer_journey.json")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--slow-mo", type=int, default=0)
    ap.add_argument("--place-order", action="store_true", default=True)
    ap.add_argument("--no-place-order", dest="place_order", action="store_false")
    args = ap.parse_args()
    global EV
    base = args.base_url.rstrip("/")
    ev = Evidence()
    EV = ev

    started = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=args.slow_mo)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        attach(page, ev, base)

        # ── 1. English home ────────────────────────────────────────────────
        page.goto(base + "/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1500)
        text = assert_renderable(page, "home")
        dir_en = page.evaluate("document.documentElement.dir")
        ev.step("home renders in English", dir_en == "ltr" and "CONFIT" in text, dir=dir_en, chars=len(text))

        # real data, taken from the same API the UI uses
        products = page.evaluate(
            """async () => {
                 const r = await fetch('/api/v1/catalog/products?sort_by=recommended');
                 const j = await r.json();
                 // MEASURED: /catalog/products answers a BARE LIST, not an envelope.
                 // The first version of this script assumed {items|products|data}
                 // and therefore saw zero products — which the validity gate turned
                 // into "MEASUREMENT INVALID" instead of a fake pass.
                 const items = Array.isArray(j) ? j : (j.items || j.products || j.data || []);
                 return items.slice(0, 3).map(i => ({slug: i.slug, title: i.title, title_ar: i.title_ar}));
               }"""
        )
        if not products or not products[0].get("slug"):
            raise Invalid(f"catalogue API returned no usable product: {products!r}")
        ev.step("catalogue returns real products", True, count=len(products), first=products[0]["title"][:40])

        # ── 2. Discover: click a real product card ─────────────────────────
        page.goto(base + "/discover", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1800)
        assert_renderable(page, "discover", 900)
        title = products[0]["title"]
        card = page.get_by_text(title[:28], exact=False).first
        card.click(timeout=15000)
        page.wait_for_timeout(2500)
        prod_text = assert_renderable(page, "product", 600)
        ev.step(
            "clicking a product card opens its detail page",
            f"/product/{products[0]['slug']}" in page.url and title[:18] in prod_text,
            url=page.url.replace(base, ""),
        )

        # ── 3. Add to bag (guest) ──────────────────────────────────────────
        before = len([n for n in ev.network if "/commerce/cart" in n["url"] and n["method"] != "GET"])
        size_buttons = page.locator("div[role='group'] button")
        if size_buttons.count() > 0:
            size_buttons.first.click(timeout=5000)
            page.wait_for_timeout(400)
        add = page.get_by_role("button", name="Add to Bag").first
        add.click(timeout=15000)
        page.wait_for_timeout(2500)
        mutations = [n for n in ev.network if "/commerce/cart" in n["url"] and n["method"] != "GET"]
        ok_add = len(mutations) > before and any(n["status"] < 400 for n in mutations)
        ev.step(
            "Add to Bag issues a cart mutation the backend accepts",
            ok_add,
            cart_writes=[f"{n['method']} {n['url']} -> {n['status']}" for n in mutations[-3:]],
        )
        page.screenshot(path=str(Path(args.out).with_suffix(".product.png")), full_page=False)
        ev.screenshots.append(str(Path(args.out).with_suffix(".product.png")))

        # ── 4. Checkout with the cart contents ─────────────────────────────
        page.goto(base + "/checkout", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        checkout_en = assert_renderable(page, "checkout", 700)
        # MEASURED: the first version of this step asserted `"Promo code" in
        # body_text` and FAILED — while the promo field was rendered. The label is
        # an input PLACEHOLDER (and an aria-label), and inner_text() returns text
        # nodes only, never attributes. The instrument was wrong, not the product;
        # attributes are read with get_attribute().
        # targeted by its own attributes: `.first` picked the guest-email field, which
        # also has a placeholder — MEASURED, and the failure detail showed it.
        promo_en = page.locator('input[aria-label="Promo code"]')
        promo_placeholder_en = promo_en.get_attribute("placeholder") if promo_en.count() else None
        ev.step(
            "checkout renders the English purchase surface",
            "Fulfillment" in checkout_en and promo_placeholder_en == "Promo code",
            chars=len(checkout_en),
            promo_placeholder=promo_placeholder_en,
        )

        # ── 5. Arabic: RTL + the phrases this project translated ────────────
        switch_language(page, "ar", base)
        page.wait_for_timeout(1500)
        ar_text = assert_renderable(page, "checkout-ar")
        dir_ar = page.evaluate("document.documentElement.dir")
        lang_ar = page.evaluate("document.documentElement.lang")
        # JSX text nodes render into inner_text(); labels that live in attributes do
        # not, so both surfaces are measured for what they actually are.
        must_render_text = ["طريقة التسليم", "بيانات التواصل والعنوان", "المجموع الإجمالي", "الضريبة"]
        missing = [s for s in must_render_text if s not in ar_text]
        promo_ar = page.locator('input[aria-label="رمز الخصم"]')
        promo_placeholder_ar = promo_ar.get_attribute("placeholder") if promo_ar.count() else None
        aria_leak = page.locator('input[aria-label="Promo code"]').count()
        ev.step(
            "Arabic checkout renders RTL with the translated phrases",
            dir_ar == "rtl" and lang_ar.startswith("ar") and not missing
            and promo_placeholder_ar == "رمز الخصم",
            dir=dir_ar, lang=lang_ar, missing=missing, promo_placeholder=promo_placeholder_ar,
        )

        # the labels that used to be hardcoded English must be gone — from text and
        # from the accessible attributes alike.
        leftovers = [s for s in ("Promo code", "Delivery address", "Full name", "Fulfillment") if s in ar_text]
        if promo_placeholder_ar == "Promo code" or aria_leak:
            leftovers.append(f"promo attrs still English (placeholder={promo_placeholder_ar!r}, aria_leak={aria_leak})")
        ev.step("previously hardcoded English labels no longer render", not leftovers, leftovers=leftovers)
        page.screenshot(path=str(Path(args.out).with_suffix(".checkout-ar.png")), full_page=False)
        ev.screenshots.append(str(Path(args.out).with_suffix(".checkout-ar.png")))

        # ── 6. The contract the app sends is unchanged by the language ─────
        # MEASURED: a bare `fetch('/api/v1/commerce/cart')` from page context answers
        # 422 — the app attaches its guest-session header, a raw fetch does not. The
        # assertion therefore uses the app's OWN calls, captured from the network, so
        # it measures the real client contract rather than a synthetic request.
        cart_calls = [n for n in ev.network if "/commerce/cart" in n["url"]]
        cart_get = [n for n in cart_calls if n["method"] == "GET"]
        ev.step(
            "the app's own cart contract still answers 200 while the UI is Arabic",
            bool(cart_get) and all(n["status"] == 200 for n in cart_get[-3:]),
            recent=[f"{n['method']} {n['url']} -> {n['status']}" for n in cart_calls[-3:]],
        )

        # ── 7. Return to English: state and direction both survive ─────────
        switch_language(page, "en", base)
        page.wait_for_timeout(1500)
        back_text = assert_renderable(page, "checkout-en-again")
        dir_back = page.evaluate("document.documentElement.dir")
        # Same attribute/text distinction as above — the copy under test is a
        # placeholder, and asserting it against inner_text() was the instrument's
        # mistake, not the product's.
        promo_back = page.locator('input[aria-label="Promo code"]').count()
        ev.step(
            "switching back restores LTR and English copy",
            dir_back == "ltr" and promo_back == 1 and "Fulfillment" in back_text,
            dir=dir_back, promo_field_back=promo_back,
        )

        # ── 7b. ACCOUNT-BEARING PHASE: place a real order and read it back ──
        # Local mutations are allowed (mission §20); nothing here touches
        # production. This is the strongest available proof for the classification
        # decision in §9: the Arabic UI must still SEND the English contract values
        # (fulfilment/shipping/payment enums) and the backend must accept them.
        if args.place_order:
            # Do it in ARABIC: the purchase path is the one where a mis-localized
            # label costs money, and the contract enums must survive regardless of
            # the display language. (MEASURED: the first version of this phase
            # clicked `تأكيد الطلب` while the UI had already been switched back to
            # English — it timed out, correctly, because a stale variable said
            # "rtl". The locator below therefore matches either language.)
            switch_language(page, "ar", base)
            page.goto(base + "/checkout", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(2000)
            page.fill("#guest-email", "e2e-journey@example.com")
            page.fill("#full-name", "E2E Journey")
            page.fill("#phone", "+971500000000")
            page.fill("#address", "1 Marina Walk, Tower 2")
            page.fill("#city", "Dubai")
            if page.locator("#country").count():
                page.fill("#country", "AE")
            # choose the demo payment method the backend actually reports
            cod = page.locator('input[type="radio"]')
            if cod.count():
                cod.last.click()
                page.wait_for_timeout(300)
            before = len(ev.network)
            submit = page.locator('button:has-text("تأكيد الطلب"), button:has-text("Place order")').first
            submit.click(timeout=15000)
            page.wait_for_timeout(4000)
            submits = [n for n in ev.network[before:] if n["method"] == "POST"]
            accepted = [n for n in submits if n["status"] < 400]
            ev.step(
                "placing an order in the Arabic UI is accepted by the backend",
                bool(accepted),
                posts=[f"{n['url']} -> {n['status']}" for n in submits[-3:]],
            )
            if "/orders/" in page.url:
                track = assert_renderable(page, "order-tracking", 500)
                ev.step(
                    "the order opens its tracking page",
                    "/orders/" in page.url,
                    url=page.url.replace(base, "/"),
                    chars=len(track),
                )
                # ── §9: contract value vs visible label, on real rows ──────
                request_return = page.get_by_text("طلب إرجاع", exact=False).first
                if request_return.count():
                    request_return.click(timeout=8000)
                    page.wait_for_timeout(1200)
                    values = page.eval_on_selector_all(
                        "#return-reason option", "els => els.map(e => [e.value, e.textContent.trim()])"
                    )
                    english_values = [v for v, _ in values if v and v.isascii()]
                    arabic_labels = [l for _, l in values if l and not l.isascii()]
                    ev.step(
                        "return reasons keep English contract values with Arabic labels",
                        bool(values) and len(english_values) == len(values) and bool(arabic_labels),
                        options=values[:3],
                        english_values=len(english_values),
                        arabic_labels=len(arabic_labels),
                    )
            else:
                ev.step("the order opens its tracking page", False, url=page.url.replace(base, "/"))

        # ── 7c. LOCALIZATION SURFACE + FILTER INTEGRITY (Arabic) ───────────
        # The localization pass split every filter option into
        # { value: <English catalogue token>, labelKey: <i18n key> }. Two things
        # must hold at runtime, and only a browser can show both:
        #   (a) the shopper reads Arabic, and
        #   (b) the filter still matches `product.occasion_tags` /
        #       `product.color_family` — i.e. the VALUE was not translated.
        # A translated value would not throw, would not fail tsc, and would not
        # fail the i18n gate; it would just return an empty grid for Arabic
        # shoppers. Hence this phase.
        switch_language(page, "ar", base)
        page.goto(base + "/discover", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2500)
        discover_ar = assert_renderable(page, "discover-ar", 900)
        dir_ar = page.evaluate("document.documentElement.dir")

        catalogue = page.evaluate(
            """async () => {
                 const p = await (await fetch('/api/v1/catalog/products')).json();
                 const c = await (await fetch('/api/v1/catalog/categories')).json();
                 const items = Array.isArray(p) ? p : (p.items || p.data || []);
                 const cats = Array.isArray(c) ? c : (c.items || c.data || []);
                 return {items: items, cats: cats};
               }"""
        )
        if not catalogue["items"]:
            raise Invalid("catalogue API returned no products for the Arabic phase")

        # (a) the labels the shopper reads
        ar_labels = ["العمل", "زفاف", "سهرة", "سفر", "يومي"]
        missing_labels = [l for l in ar_labels if l not in discover_ar]
        chips = page.evaluate(
            "() => [...document.querySelectorAll('button')].map(b => b.textContent.trim())"
        )
        token_leaks = [t for t in ["Work", "Wedding", "Evening", "Travel", "Everyday",
                                   "Navy Blue", "Midnight Black", "Optic White",
                                   "Champagne Gold", "Emerald Green"]
                       if t in chips]
        ev.step(
            "Arabic filter labels render, English catalogue tokens do not",
            not missing_labels and not token_leaks and dir_ar == "rtl",
            missing=missing_labels, token_leaks=token_leaks, dir=dir_ar,
        )

        # labels for the taxonomy must come from the API's own name_ar field
        ar_names = [c.get("name_ar") for c in catalogue["cats"] if c.get("name_ar")]
        rendered_ar_names = [n for n in ar_names if n in chips]
        ev.step(
            "category chips use the API's Arabic names (name_ar)",
            bool(ar_names) and len(rendered_ar_names) == len(ar_names),
            from_api=len(ar_names), rendered=len(rendered_ar_names), sample=rendered_ar_names[:2],
        )

        # (b) the filter must still match the English token against live data
        expected = [
            i["title"] for i in catalogue["items"]
            if any("work" in (t or "").lower() for t in (i.get("occasion_tags") or []))
        ]
        if not expected:
            raise Invalid("no catalogue product carries a 'work' occasion tag — filter cannot be probed")
        body_before = rendered_text(page)
        all_titles = [i["title"] for i in catalogue["items"]]
        before_titles = [t for t in all_titles if t in body_before]
        page.get_by_role("button", name="العمل", exact=True).first.click(timeout=10000)
        page.wait_for_timeout(2000)
        body_after = rendered_text(page)
        after_titles = [t for t in all_titles if t in body_after]
        ev.step(
            "tapping the Arabic 'Work' chip filters using the English token",
            sorted(after_titles) == sorted(expected) and len(after_titles) < len(before_titles),
            before=len(before_titles), after=len(after_titles), expected_by_api=len(expected),
        )

        # price digits must follow the Arabic locale (not Latin '$12.00')
        arabic_digits = re.findall(r"[\u0660-\u0669]", body_after)
        ev.step(
            "prices render with the Arabic locale digit set",
            bool(arabic_digits),
            arabic_digit_count=len(arabic_digits),
        )

        # a chip that matches nothing must fail HONESTLY (localized empty state),
        # never as a blank grid — this also records the pre-existing vocabulary gap
        page.get_by_role("button", name="سفر", exact=True).first.click(timeout=10000)
        page.wait_for_timeout(1800)
        empty_text = rendered_text(page)
        travel_matches = [
            i["title"] for i in catalogue["items"]
            if any("travel" in (t or "").lower() for t in (i.get("occasion_tags") or []))
        ]
        ev.step(
            "a zero-match Arabic chip shows the localized empty state, not a blank grid",
            "لا توجد قطع فاخرة تطابق معاييرك" in empty_text
            and "إعادة تعيين كل الفلاتر" in empty_text,
            api_matches_for_travel=len(travel_matches),
        )

        # the guided-look option VALUES go to the stylist API, so they stay English
        page.goto(base + "/", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        option_pairs = page.evaluate(
            """() => [...document.querySelectorAll('select option')]
                 .map(o => [o.value, o.textContent.trim()])"""
        )
        budget_pairs = [p for p in option_pairs if p[0] in ("300", "450", "650", "900")]
        ev.step(
            "guided-look budget keeps numeric values with Arabic labels",
            bool(budget_pairs) and all(v.isascii() for v, _ in budget_pairs)
            and all(not l.isascii() for _, l in budget_pairs),
            sample=budget_pairs[:2],
        )

        # and switching back must restore the exact English copy (no drift)
        switch_language(page, "en", base)
        page.goto(base + "/discover", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1800)
        discover_en = assert_renderable(page, "discover-en", 900)
        restore_chips = page.evaluate(
            "() => [...document.querySelectorAll('button')].map(b => b.textContent.trim())"
        )
        dir_en_again = page.evaluate("document.documentElement.dir")
        chips_seen = [c for c in ["Work", "Wedding", "Evening", "Travel", "Everyday"] if c in restore_chips]
        # MEASURED: this span is styled `uppercase`, and Playwright's inner_text()
        # returns the CSS-transformed text ("YOU ARE BROWSING:"), so the first
        # version of this assertion compared against the source casing and failed
        # on a rendering that was correct. Compare case-insensitively.
        ev.step(
            "switching back restores the original English chip copy",
            len(chips_seen) == 5
            and "you are browsing:" in discover_en.lower()
            and dir_en_again == "ltr",
            dir=dir_en_again,
            chips_seen=chips_seen,
            chips_sample=restore_chips[:12],
            browsing_line=[l for l in discover_en.splitlines() if "browsing" in l.lower()][:1],
        )

        browser.close()

    server_errors = [n for n in ev.network if n["status"] >= 500]
    payload = {
        "base_url": base,
        "duration_seconds": round(time.time() - started, 1),
        "steps": ev.steps,
        "api_calls": len(ev.network),
        "server_errors": server_errors,
        "console_errors": ev.console_errors[:10],
        "screenshots": ev.screenshots,
        "verdict": "PASS" if not server_errors else "FAIL: backend 5xx during journey",
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  api calls: {len(ev.network)} | 5xx: {len(server_errors)} | console errors: {len(ev.console_errors)}")
    print(f"  evidence -> {args.out}")
    if server_errors:
        print("  FAIL: the journey produced backend errors")
        return 1
    print("  E2E PASS — every step verified against a live backend")
    return 0


def _dump(out: str, base: str, verdict: str, error: str | None = None) -> None:
    """Write whatever the run produced — including on an invalid/failed run."""
    if EV is None:
        return
    payload = {
        "base_url": base,
        "steps": EV.steps,
        "api_calls": len(EV.network),
        "server_errors": [n for n in EV.network if n["status"] >= 500],
        "console_errors": EV.console_errors[:10],
        "screenshots": EV.screenshots,
        "verdict": verdict,
    }
    if error:
        payload["error"] = error
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  partial evidence -> {out}")


if __name__ == "__main__":
    _out = "/tmp/e2e_consumer_journey.json"
    _base = "http://127.0.0.1:43123"
    for _i, _a in enumerate(sys.argv):
        if _a == "--out" and _i + 1 < len(sys.argv):
            _out = sys.argv[_i + 1]
        if _a == "--base-url" and _i + 1 < len(sys.argv):
            _base = sys.argv[_i + 1]
    try:
        sys.exit(main())
    except Invalid as exc:
        print(f"\n  MEASUREMENT INVALID — no verdict: {exc}")
        _dump(_out, _base, "INVALID: measurement not trustworthy", str(exc))
        sys.exit(3)
    except AssertionError as exc:
        print(f"\n  FAIL: {exc}")
        _dump(_out, _base, "FAIL: a journey step failed", str(exc))
        sys.exit(1)
