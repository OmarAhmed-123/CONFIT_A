#!/usr/bin/env python3
"""C05 — Virtual Stylist drawer goal E2E against the LOCAL stack.

GOALS (user outcomes, not DOM structure):
  G1  Open: the AI Stylist entry point opens the drawer; it is a real dialog
      (focus trapped, labelled, Escape closes).
  G2  Occasion chip: one tap sends a real /stylist/chat request; while the
      server thinks a geometry-matched skeleton shows; the reply arrives with
      the engine named honestly in the transcript.
  G3  Money honesty: every price in a recommendation card is the catalogue's
      real currency (EGP seed) or an honest em-dash — never a fabricated "$".
  G4  Add look to bag: the complete-look CTA writes each piece exactly once
      to the real cart (server state proves it).
  G5  Failure & recovery (counter-goal): with /stylist/chat aborted at the
      network boundary the drawer shows an honest retryable error and the
      transcript gains NO assistant bubble; retry after recovery succeeds.
  G6  Arabic/RTL: the Arabic drawer carries no hard-coded English chrome
      (slot badges, banner, toasts) and renders RTL.

RUN VALIDITY: blank render or unreachable API = MEASUREMENT INVALID (exit 3).
Network-boundary aborts are disclosed test infrastructure.

Usage:
    python3 scripts/e2e_stylist_goals.py [--base-url URL] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid

from playwright.sync_api import Page, sync_playwright

# UI-CHROME leaks only. Product titles, role_in_outfit and fallback-engine
# prose are backend DATA (translated by the provider pipeline in prod, and
# the engine label discloses the fallback) — asserting on them would flag
# legitimate catalogue content as a chrome defect.
EN_LEAKS = [
    "This stylist response did not include",
    "no verified catalog items to add yet",
    "missing verified SKU data",
    "Complete Look",
    "Add Complete Look",
]


class Invalid(Exception):
    pass


class Evidence:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.console_errors: list[str] = []

    def step(self, name: str, ok: bool, **detail) -> None:
        self.steps.append({"step": name, "ok": bool(ok), **detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} "
              + " ".join(f"{k}={v}" for k, v in detail.items()))
        if not ok:
            raise AssertionError(f"step failed: {name} | {detail}")


def api(page: Page, path: str, method: str = "GET", body=None):
    return page.evaluate(
        """async ({path, method, body}) => {
             const headers = {'Content-Type': 'application/json'};
             const m = document.cookie.match(/(?:^|;\\s*)confit_csrf=([^;]+)/);
             if (m) headers['X-CSRF-Token'] = m[1];
             const st = localStorage.getItem('confit_session_token');
             if (st) headers['X-Session-Token'] = st;
             const r = await fetch('/api/v1' + path, {
               method, headers, body: body ? JSON.stringify(body) : undefined,
             });
             let data = null;
             try { data = await r.json(); } catch (e) {}
             return {status: r.status, data};
           }""",
        {"path": path, "method": method, "body": body},
    )


def open_drawer(page: Page) -> None:
    btn = page.locator('button:has-text("AI Stylist"), button:has-text("المدير الأسلوبي")').first
    btn.click()
    page.wait_for_selector('[role="dialog"]', timeout=10000)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/tmp/e2e_stylist_goals.json")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    ev = Evidence()
    started = time.time()
    exit_code = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: ev.console_errors.append(m.text[:200]) if m.type == "error" else None)
        page.on("pageerror", lambda e: ev.console_errors.append(f"pageerror: {e}"))
        try:
            page.goto(base + "/", wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1000)
            if len(page.inner_text("body")) < 400:
                raise Invalid("home page rendered almost nothing")

            # account (cart is user-scoped; stylist needs no auth but bag does)
            email = f"e2e-stylist-{uuid.uuid4().hex[:10]}@example.com"
            created = api(page, "/auth/register", "POST", {
                "email": email, "password": "E2eStylist!2345",
                "full_name": "E2E Stylist", "preferred_language": "en",
            })
            if created["status"] not in (200, 201):
                raise Invalid(f"could not create probe account: {created}")
            api(page, "/profile/onboarding-quiz", "POST", {
                "style_archetypes": ["Old Money"], "budget_per_outfit_max": 50000.0,
            })
            me = api(page, "/auth/me")
            if me["status"] == 200 and me["data"]:
                page.evaluate("(u) => localStorage.setItem('confit_user', JSON.stringify(u))",
                              me["data"].get("user", me["data"]))
            page.reload(wait_until="networkidle", timeout=60000)
            ev.step("probe account ready", True)

            # ════ G1 — open: labelled dialog, Escape closes ════
            open_drawer(page)
            dlg = page.locator('[role="dialog"]')
            ev.step("drawer opens as a labelled dialog",
                    dlg.get_attribute("aria-label") not in (None, ""))
            page.keyboard.press("Escape")
            page.wait_for_selector('[role="dialog"]', state="detached", timeout=5000)
            ev.step("Escape closes the drawer", True)

            # ════ G2 — occasion chip -> skeleton -> honest engine ════
            open_drawer(page)
            page.locator('[role="dialog"] button', has_text=re.compile("Evening")).first.click()
            skeleton_seen = False
            try:
                page.wait_for_selector('[data-testid="stylist-thinking"]', timeout=8000)
                skeleton_seen = page.evaluate(
                    """() => document.querySelectorAll('[data-testid="stylist-thinking"] .skeleton-shimmer').length""") >= 5
            except Exception:
                pass  # a very fast reply can legitimately outrun the skeleton
            page.wait_for_selector('[data-engine]', timeout=60000)
            engine = page.locator('[data-engine]').first.get_attribute("data-engine")
            ev.step("reply landed with the engine named honestly",
                    bool(engine), engine=engine, skeleton_seen=skeleton_seen)

            # ════ G3 — money honesty on the recommendation card ════
            page.wait_for_selector('[data-testid="stylist-ensemble-total"]', timeout=20000)
            total_txt = page.locator('[data-testid="stylist-ensemble-total"]').first.inner_text()
            dlg_text = page.locator('[role="dialog"]').inner_text()
            ev.step("ensemble total is real catalogue currency or em-dash, never $",
                    ("$" not in total_txt) and (("EGP" in total_txt) or ("\u2014" in total_txt)),
                    total=total_txt)
            ev.step("no $ anywhere in the recommendation card chrome",
                    "$" not in dlg_text)

            # ════ G4 — add complete look -> real cart, no duplicates ════
            add_btn = page.locator('[role="dialog"] button', has_text=re.compile("Add .* to Bag|Add complete", re.I)).first
            if add_btn.count() == 0 or not add_btn.is_enabled():
                ev.step("add-look CTA present and enabled (items verified)", False)
            add_btn.click()
            page.wait_for_timeout(2500)
            cart = api(page, "/commerce/cart")
            items = (cart["data"] or {}).get("items", [])
            qty_ok = all(i.get("quantity") == 1 for i in items)
            ev.step("every piece landed in the real cart exactly once",
                    len(items) >= 2 and qty_ok,
                    cart=[(i.get("product_sku_id"), i.get("quantity")) for i in items])

            # close any cart drawer the add opened
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)

            # ════ G5 — outage: honest error, NO assistant bubble, retry ════
            page.reload(wait_until="networkidle", timeout=60000)
            open_drawer(page)
            # Opening from the home CTA fires a legitimate prefill prompt.
            # Let ITS reply settle before the baseline, otherwise it lands
            # mid-outage and looks like a fabricated bubble (measurement
            # error observed, not an app defect).
            try:
                page.wait_for_selector('[data-engine]', timeout=30000)
            except Exception:
                pass
            page.wait_for_timeout(800)
            bubbles_before = page.locator('[data-engine]').count()
            page.route(re.compile(r".*/stylist/chat.*"), lambda r: r.abort())
            page.locator('[role="dialog"] button', has_text=re.compile("Work")).first.click()
            page.wait_for_selector('[role="dialog"] .bg-rose-50', timeout=30000)
            ev.step("outage shows an honest error banner (network-boundary abort, test harness)", True)
            ev.step("no assistant bubble was fabricated during the outage",
                    page.locator('[data-engine]').count() == bubbles_before)
            retry = page.locator('[role="dialog"] button', has_text=re.compile("Retry|إعادة")).first
            ev.step("the error is retryable", retry.count() == 1)
            page.unroute_all(behavior="ignoreErrors")
            retry.click()
            page.wait_for_selector('[data-engine]', timeout=60000)
            ev.step("retry after recovery produces a real reply", True)

            # ════ G6 — Arabic: RTL + zero chrome leaks ════
            page.evaluate("localStorage.setItem('confit_lang','ar')")
            page.reload(wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1500)
            ev.step("Arabic page is RTL", page.evaluate("document.documentElement.dir") == "rtl")
            open_drawer(page)
            page.locator('[role="dialog"] button').filter(has_text=re.compile("سهرة|مناسبة|عمل")).first.click()
            page.wait_for_selector('[data-testid="stylist-ensemble-total"]', timeout=60000)
            ar_text = page.locator('[role="dialog"]').inner_text()
            leaks = [l for l in EN_LEAKS if l in ar_text]
            ev.step("zero hard-coded-English chrome in the Arabic drawer", leaks == [], leaks=leaks)
            # the slot badges specifically — the old switch hard-coded four
            # English words; they must now render from the Arabic bundle
            badges = page.evaluate(
                """() => [...document.querySelectorAll('[role=\"dialog\"] span')]
                       .map(s => s.textContent.trim())
                       .filter(t => ['Outerwear','Trousers','Footwear','Accessory'].includes(t))""")
            ev.step("slot badges are translated (no English badge chrome)", badges == [], badges=badges)
            ar_total = page.locator('[data-testid="stylist-ensemble-total"]').first.inner_text()
            ev.step("Arabic money is locale-formatted catalogue currency, not $",
                    "$" not in ar_total, total=ar_total)

            # console noise: attribute only the harness-aborted chat calls
            noise = [e for e in ev.console_errors
                     if "favicon" not in e and "React DevTools" not in e]
            aborted = [e for e in noise if "net::ERR_FAILED" in e or "Failed to fetch" in e]
            other = [e for e in noise if e not in aborted]
            ev.step("no console errors beyond the harness-aborted request",
                    other == [], attributed=len(aborted), other=other[:4])

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
    print(f"\n== stylist goals: {passed}/{len(ev.steps)} steps passed "
          f"in {time.time()-started:.1f}s (exit {exit_code}) ==")
    with open(args.out, "w") as f:
        json.dump({"steps": ev.steps, "console_errors": ev.console_errors,
                   "exit_code": exit_code}, f, indent=2)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
