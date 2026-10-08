#!/usr/bin/env python3
"""C04 — Outfit Builder goal E2E (/builder, /outfits/:id) against the LOCAL stack.

GOALS (user outcomes, not DOM structure):
  G1  Compose: picking catalog pieces fills their natural slots and the running
      total equals the REAL arithmetic sum of the selected pieces' SKU prices
      (price_override || base_price), formatted in the catalog currency (EGP),
      never a hard-coded "$".
  G2  Undoable remove: clearing a slot offers Undo, and Undo really restores it.
  G3  Save: the save CTA claims success only after POST /outfits resolves, and
      the look then exists server-side AND on /my-looks.
  G4  Edit alias: /outfits/:id loads that look, Update persists in place —
      no duplicate look is created.
  G5  Failure & recovery (counter-goal): with POST /outfits aborted at the
      network boundary the CTA reports an honest error and the look is NOT on
      the server; a retry after recovery succeeds.
  G6  Add-to-bag: the whole look lands in the cart with quantity 1 per piece —
      the in-flight guard means no silent duplicates.
  G7  Keyboard: Enter on a focused palette card adds the piece (BUILDER-01).
  G8  Arabic/RTL: the page renders RTL with zero hard-coded-English leakage
      and locale-formatted money.

RUN VALIDITY: a blank render or an unreachable API is MEASUREMENT INVALID
(exit 3), never a pass. Network-boundary patches (route.abort) are test
infrastructure and are disclosed as such — nothing is claimed as server data.

Usage:
    python3 scripts/e2e_builder_goals.py [--base-url URL] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid

from playwright.sync_api import Page, sync_playwright

MIN_RENDERED_TEXT = 600
EN_LEAKS = [
    "Sticky Look Summary",
    "Add Complete Look to Bag",
    "Profile Target Allocation",
    "Drop a piece here",
    "Use Tailored Power",
    "Avoid the blank-canvas problem",
    "Drag Pieces from the Multi-Brand Catalog",
    "My Custom Tailored Ensemble",
    "Loading this look",
    "Checking size",
    "Awaiting items",
]


class Invalid(Exception):
    """The measurement itself is not trustworthy — never a pass."""


class Evidence:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.network: list[dict] = []
        self.console_errors: list[str] = []

    def step(self, name: str, ok: bool, **detail) -> None:
        self.steps.append({"step": name, "ok": bool(ok), **detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} "
              + " ".join(f"{k}={v}" for k, v in detail.items()))
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


def switch_language(page: Page, lang: str) -> None:
    page.evaluate("(l) => localStorage.setItem('confit_lang', l)", lang)
    page.reload(wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(1500)


def parse_amount(text: str) -> float:
    """Parse a localized money string to a float (Latin or Arabic-Indic digits).
    Currency marks like "ج.م." contain dots, so extract the numeric TOKEN
    first instead of stripping non-digits globally."""
    t = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٬٫", "0123456789,."))
    m = re.search(r"\d[\d,]*(?:\.\d+)?", t)
    if not m:
        return 0.0
    return float(m.group(0).replace(",", ""))


def api(page: Page, path: str, method: str = "GET", body=None):
    return page.evaluate(
        """async ({path, method, body}) => {
             const headers = {'Content-Type': 'application/json'};
             // Double-submit CSRF: echo the readable confit_csrf cookie,
             // exactly like the app's own apiClient does.
             const m = document.cookie.match(/(?:^|;\\s*)confit_csrf=([^;]+)/);
             if (m) headers['X-CSRF-Token'] = m[1];
             // The cart is keyed by the persistent session token, exactly
             // like the app's own apiClient sends on every request.
             const st = localStorage.getItem('confit_session_token');
             if (st) headers['X-Session-Token'] = st;
             const r = await fetch('/api/v1' + path, {
               method,
               headers,
               body: body ? JSON.stringify(body) : undefined,
             });
             let data = null;
             try { data = await r.json(); } catch (e) {}
             return {status: r.status, data};
           }""",
        {"path": path, "method": method, "body": body},
    )


def filled_slots(page: Page) -> int:
    return page.evaluate(
        """() => [...document.querySelectorAll('[data-testid^=\"slot-\"]')]
                 .filter(s => s.querySelector('img')).length"""
    )


def total_text(page: Page) -> str:
    return page.inner_text('[data-testid="builder-running-total"]')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/tmp/e2e_builder_goals.json")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    ev = Evidence()
    started = time.time()
    exit_code = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        attach(page, ev, base)
        try:
            page.goto(base + "/", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1000)

            # ── account on the LOCAL stack only (cookies land in this context)
            email = f"e2e-builder-{uuid.uuid4().hex[:10]}@example.com"
            created = api(page, "/auth/register", "POST", {
                "email": email, "password": "E2eBuilder!2345",
                "full_name": "E2E Builder", "preferred_language": "en",
            })
            if created["status"] not in (200, 201):
                raise Invalid(f"could not create the probe account: {created}")
            ev.step("probe account created on the local stack", True, status=created["status"])

            # Fresh accounts are bounced to /profile?onboarding=1 by the
            # OnboardingGate until a style profile exists. Complete the quiz
            # through the app's own API — including a REAL per-outfit budget
            # that G-budget asserts the builder actually uses.
            BUDGET = 20000.0
            quiz = api(page, "/profile/onboarding-quiz", "POST", {
                "style_archetypes": ["Old Money"],
                "budget_per_outfit_max": BUDGET,
            })
            if quiz["status"] not in (200, 201):
                raise Invalid(f"could not complete onboarding quiz: {quiz}")
            me = api(page, "/auth/me")
            if me["status"] == 200 and me["data"]:
                user_obj = me["data"].get("user", me["data"])
                page.evaluate("(u) => localStorage.setItem('confit_user', JSON.stringify(u))",
                              user_obj)
            ev.step("style profile completed (has_profile gate satisfied)", True,
                    budget_per_outfit_max=BUDGET)
            page.reload(wait_until="networkidle", timeout=60000)

            # ── catalog ground truth from the API (not from the screen)
            catalog = api(page, "/catalog/products")
            items = catalog["data"] if isinstance(catalog["data"], list) else catalog["data"].get("items", [])
            if not items:
                raise Invalid("catalog API returned no products")
            currency = items[0].get("currency") or "USD"
            details = {}
            for it in items:
                d = api(page, f"/catalog/products/{it['slug']}")
                if d["status"] == 200:
                    details[it["title"]] = d["data"]
            ev.step("catalog ground truth loaded", len(details) == len(items),
                    products=len(items), currency=currency)

            def sku_price(title: str) -> float:
                d = details[title]
                skus = d.get("skus") or []
                pick = next((s for s in skus if s.get("is_in_stock") and s.get("stock_level", 0) > 0),
                            skus[0] if skus else None)
                if pick and pick.get("price_override") is not None:
                    return float(pick["price_override"])
                return float(d["base_price"])

            # ════ G1 — compose with real arithmetic ════
            page.goto(base + "/builder", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1200)
            assert_renderable(page, "builder-en")

            page.wait_for_selector('button[aria-label^="Add "][aria-label$=" to outfit"]',
                                   timeout=20000)
            add_buttons = page.locator('button[aria-label^="Add "][aria-label$=" to outfit"]')
            n_pal = add_buttons.count()
            ev.step("palette renders catalog pieces", n_pal >= 3, palette_buttons=n_pal)

            for i in range(n_pal):
                if filled_slots(page) >= 3:
                    break
                add_buttons.nth(i).click()
                page.wait_for_timeout(600)
            ev.step("three distinct slots filled by clicking", filled_slots(page) >= 3)

            # Ground truth of WHAT is on the canvas comes from the remove
            # buttons' accessible names ("Remove {title} from {slot}") — a
            # same-slot click REPLACES the piece, so counting clicks would lie.
            def canvas_titles() -> list[str]:
                labels = page.evaluate(
                    """() => [...document.querySelectorAll('button[aria-label^="Remove "]')]
                             .map(b => b.getAttribute('aria-label'))"""
                )
                return [l[len("Remove "):l.rindex(" from ")] for l in labels]

            added_titles = canvas_titles()
            expected_sum = sum(sku_price(t) for t in added_titles)

            page.wait_for_function(
                """(exp) => {
                     const el = document.querySelector('[data-testid="builder-running-total"]');
                     if (!el) return false;
                     const t = el.textContent.replace(/[^0-9.,]/g, '').replace(/,/g, '');
                     return Math.abs(parseFloat(t) - exp) < 0.01;
                   }""",
                arg=round(expected_sum, 2), timeout=8000)
            shown = total_text(page)
            ev.step("running total equals the real SKU arithmetic", True,
                    shown=shown, expected=round(expected_sum, 2))
            ev.step("total shows the catalog currency, not a hard-coded $",
                    ("$" not in shown) if currency != "USD" else True,
                    currency=currency, shown=shown)
            bag_cta = page.get_by_test_id("builder-add-all").inner_text()
            ev.step("bag CTA quotes the same honest figure",
                    abs(parse_amount(bag_cta) - round(expected_sum, 2)) < 0.01, cta=bag_cta)

            # ════ G-budget — the PROFILE budget drives the tracker ════
            body_txt = rendered_text(page)
            budget_shown = f"{BUDGET:,.2f}" in body_txt.replace("\u00a0", " ")
            over_state = expected_sum > BUDGET
            # EN i18n: over => "Exceeds Allocation", under => "Within Budget"
            over_badge_visible = "Exceeds Allocation" in body_txt
            ev.step("profile budget_per_outfit_max is the allocated budget on screen",
                    budget_shown, budget=BUDGET)
            ev.step("over/under verdict matches real arithmetic vs the profile budget",
                    over_badge_visible == over_state,
                    total=round(expected_sum, 2), budget=BUDGET, over=over_state)

            # ════ G2 — undoable remove ════
            victim = added_titles[0]
            remove_btn = page.locator(f'button[aria-label^="Remove {victim} from"]').first
            remove_btn.click()
            page.wait_for_timeout(500)
            slots_after_remove = filled_slots(page)
            ev.step("slot cleared on remove", slots_after_remove == 2, filled=slots_after_remove)
            undo = page.get_by_role("button", name="Undo removal")
            undo.first.click(timeout=5000)
            page.wait_for_timeout(500)
            ev.step("Undo really restores the piece", filled_slots(page) == 3,
                    restored=victim)

            # ════ G3 — save is honest and lands server-side ════
            look_name = f"E2E Look {uuid.uuid4().hex[:6]}"
            name_input = page.get_by_role("textbox", name="Outfit name")
            name_input.fill(look_name)
            save = page.get_by_test_id("save-look-cta")
            save.click()
            page.wait_for_function(
                """() => document.querySelector('[data-testid="save-look-cta"]')
                           ?.getAttribute('data-state') === 'success'""",
                timeout=15000)
            looks = api(page, "/outfits")
            mine = [o for o in (looks["data"] or []) if o.get("title") == look_name]
            ev.step("saved look exists server-side", len(mine) == 1,
                    outfit_id=mine[0]["id"] if mine else None)
            outfit_id = mine[0]["id"]
            page.goto(base + "/my-looks", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1500)
            # The look title renders as an editable <input> — read values,
            # not innerText (inputs are invisible to innerText).
            titles_on_page = page.evaluate(
                "[...document.querySelectorAll('input')].map(i => i.value)")
            ev.step("saved look visible on /my-looks", look_name in titles_on_page)

            # ════ G4 — /outfits/:id edits in place, no duplicate ════
            page.goto(f"{base}/outfits/{outfit_id}", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1500)
            hydrated = page.get_by_role("textbox", name="Outfit name").input_value()
            ev.step("edit alias hydrates the saved look", hydrated == look_name, value=hydrated)
            new_name = look_name + " v2"
            page.get_by_role("textbox", name="Outfit name").fill(new_name)
            count_before = len(api(page, "/outfits")["data"] or [])
            page.get_by_test_id("save-look-cta").click()
            page.wait_for_function(
                """() => document.querySelector('[data-testid="save-look-cta"]')
                           ?.getAttribute('data-state') === 'success'""",
                timeout=15000)
            after = api(page, "/outfits")["data"] or []
            renamed = [o for o in after if o.get("title") == new_name]
            ev.step("update persists in place — same id, no duplicate",
                    len(renamed) == 1 and renamed[0]["id"] == outfit_id
                    and len(after) == count_before,
                    total_looks=len(after))

            # ════ G5 — failure & recovery at the network boundary ════
            # DISCLOSED TEST PATCH: POST /outfits is aborted by the harness to
            # simulate an outage; nothing here is claimed as server behaviour.
            page.goto(base + "/builder", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1200)
            add_buttons = page.locator('button[aria-label^="Add "][aria-label$=" to outfit"]')
            add_buttons.nth(0).click()
            page.wait_for_timeout(800)
            fail_name = f"E2E Fail {uuid.uuid4().hex[:6]}"
            page.get_by_role("textbox", name="Outfit name").fill(fail_name)

            harness_aborts = []

            def abort_outfit_post(route):
                if route.request.method == "POST":
                    harness_aborts.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()
            page.route(re.compile(r".*/api/v1/outfits(/save)?$"), abort_outfit_post)
            page.get_by_test_id("save-look-cta").click()
            page.wait_for_function(
                """() => document.querySelector('[data-testid="save-look-cta"]')
                           ?.getAttribute('data-state') === 'error'""",
                timeout=15000)
            ghost = [o for o in (api(page, "/outfits")["data"] or []) if o.get("title") == fail_name]
            ev.step("aborted save reports error and writes NOTHING server-side",
                    len(ghost) == 0, note="network-boundary abort (test harness)")
            page.unroute(re.compile(r".*/api/v1/outfits(/save)?$"))
            page.get_by_test_id("save-look-cta").click()
            page.wait_for_function(
                """() => document.querySelector('[data-testid="save-look-cta"]')
                           ?.getAttribute('data-state') === 'success'""",
                timeout=15000)
            recovered = [o for o in (api(page, "/outfits")["data"] or []) if o.get("title") == fail_name]
            ev.step("retry after recovery succeeds", len(recovered) == 1)

            # ════ G6 — whole look to bag, quantity 1 each ════
            page.goto(base + "/builder", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1200)
            add_buttons = page.locator('button[aria-label^="Add "][aria-label$=" to outfit"]')
            for i in range(add_buttons.count()):
                if filled_slots(page) >= 2:
                    break
                add_buttons.nth(i).click()
                page.wait_for_timeout(500)
            n_pieces = filled_slots(page)
            page.get_by_test_id("builder-add-all").click()
            page.wait_for_timeout(2500)
            cart = api(page, "/commerce/cart")
            cart_items = (cart["data"] or {}).get("items", [])
            ev.step("every ready piece lands in the cart with quantity 1",
                    len(cart_items) == n_pieces and all(i.get("quantity") == 1 for i in cart_items),
                    pieces=n_pieces, cart=[(i.get("product_sku_id"), i.get("quantity")) for i in cart_items])

            # ════ G7 — keyboard: Enter on a focused card adds (BUILDER-01) ════
            page.goto(base + "/builder", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1200)
            before = filled_slots(page)
            page.locator('button[aria-label^="Add "][aria-label$=" to outfit"]').first.focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(600)
            ev.step("Enter on a focused palette card adds the piece",
                    filled_slots(page) == before + 1)

            # ════ G8 — Arabic RTL, zero leakage, locale money ════
            switch_language(page, "ar")
            page.goto(base + "/builder", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1500)
            text_ar = assert_renderable(page, "builder-ar")
            ev.step("Arabic page is RTL", page.evaluate("document.documentElement.dir") == "rtl")
            ev.step("Arabic surfaces present",
                    ("ملخص الإطلالة" in text_ar) and ("منشئ" in text_ar or "الإطلالة" in text_ar))
            leaks = [s for s in EN_LEAKS if s in text_ar]
            ev.step("zero hard-coded-English leakage in Arabic", leaks == [], leaks=leaks)
            # money: add one piece, the total must not use "$" for EGP
            page.locator('button[aria-label], button').first  # noqa: silence lint
            ar_add = page.locator('[data-testid="builder-add-all"]')
            first_card = page.locator('button[aria-label]').filter(has_text=re.compile(r".+"))
            # click first palette product (aria-label is Arabic now; use grid position)
            palette_btn = page.locator('div.grid button[aria-label]').filter(
                has=page.locator("img")).first
            palette_btn.click()
            page.wait_for_timeout(800)
            shown_ar = total_text(page)
            ev.step("Arabic total avoids hard-coded $ and parses as money",
                    ("$" not in shown_ar) and parse_amount(shown_ar) > 0, shown=shown_ar)

            # The G5 harness deliberately aborted N POSTs; the browser logs
            # exactly one net::ERR_FAILED for each. Attribute those to the
            # harness and allow no OTHER console errors.
            console_noise = [e for e in ev.console_errors
                             if "favicon" not in e and "Download the React DevTools" not in e]
            err_failed = [e for e in console_noise if "net::ERR_FAILED" in e]
            other = [e for e in console_noise if "net::ERR_FAILED" not in e]
            ev.step("no console errors beyond the harness-aborted requests",
                    other == [] and len(err_failed) <= len(harness_aborts),
                    harness_aborts=len(harness_aborts),
                    attributed_err_failed=len(err_failed), other=other[:5])

        except AssertionError:
            exit_code = 1
        except Invalid as ex:
            print(f"  [INVALID] {ex}")
            exit_code = 3
        except Exception as ex:  # noqa: BLE001
            print(f"  [ERROR] {type(ex).__name__}: {ex}")
            exit_code = 2
        finally:
            browser.close()

    passed = sum(1 for s in ev.steps if s["ok"])
    print(f"\n== builder goals: {passed}/{len(ev.steps)} steps passed "
          f"in {time.time()-started:.1f}s (exit {exit_code}) ==")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"steps": ev.steps, "console_errors": ev.console_errors,
                   "network_tail": ev.network[-40:]}, fh, ensure_ascii=False, indent=2)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
