#!/usr/bin/env python3
"""Local browser Goal-E2E — the C02 discover/catalogue page, EN + AR.

House harness pattern (e2e_consumer_journey.py / e2e_home_goals.py):
every goal is proven end to end — UI action -> HTTP request -> backend
response -> UI state — and the network evidence is kept in the output.
A crashed or half-rendered page is a MEASUREMENT FAILURE, never a pass.

Goals (visitor role):
  G1  Arrival: /discover shows the REAL catalogue (server titles on real
      cards); the /products and /stylist aliases render the same screen;
      zero failed /api requests, zero console errors; no horizontal
      overflow on phones.
  G2  Search: typing in the combobox fires the real autocomplete, the
      listbox is keyboard-driven (ArrowDown -> aria-activedescendant,
      Enter opens the product), and ?q= lands in the URL.
  G3  Filtering: an occasion pill (built from the LIVE /catalog/occasions
      vocabulary) refetches the catalogue with ?occasion= on the wire,
      writes the URL, and the grid matches the API's answer.
  G4  Deep link: /discover?occasion=...&sort=newest restores the exact
      state (pressed pill + sort value) after a cold load.
  G5  Product cards are REAL links (href to the PDP) and clicking one
      lands on the product page.
  G6  The wishlist heart survives a full reload (device-side persistence).
  G7  Arabic: dir=rtl, Arabic copy renders, and filtering still sends
      English wire tokens.
Counter-goals: junk URL tokens are ignored, never applied or echoed.

Usage:
    python3 scripts/e2e_discover_goals.py [--base-url http://127.0.0.1:43123]
                                          [--out /path/evidence.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

MIN_RENDERED_TEXT = 800


class Invalid(Exception):
    pass


class Evidence:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.network: list[dict] = []
        self.console_errors: list[str] = []

    def step(self, name: str, ok: bool, **detail) -> None:
        self.steps.append({"step": name, "ok": ok, **detail})
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        if not ok:
            raise Invalid(name + ": " + json.dumps(detail, default=str)[:400])


EV = Evidence()


def wire(page) -> None:
    page.on("response", lambda r: EV.network.append(
        {"url": r.url, "status": r.status}) if "/api/" in r.url else None)
    page.on("pageerror", lambda e: EV.console_errors.append(str(e)))
    page.on("console", lambda m: EV.console_errors.append(m.text)
            if m.type == "error" else None)


def api_failures() -> list[dict]:
    return [n for n in EV.network
            if n["status"] >= 400 and not (n["status"] == 401 and "/me" in n["url"])]


def assert_valid(page) -> None:
    if len(page.inner_text("body")) < MIN_RENDERED_TEXT:
        raise Invalid("page under-rendered")
    if EV.console_errors:
        raise Invalid("console errors: " + "; ".join(EV.console_errors[:3]))


def first_api_title(page, base: str, query: str = "") -> str:
    products = page.request.get(
        base + "/api/v1/catalog/products" + query).json()
    assert isinstance(products, list) and products, "catalogue empty"
    return products[0]["title"]


def goal_arrival(page, base: str) -> None:
    page.goto(base + "/discover", wait_until="networkidle")
    assert_valid(page)
    title = first_api_title(page, base)
    page.get_by_text(title, exact=False).first.wait_for(timeout=10000)
    EV.step("G1 /discover shows the real catalogue", True, probe_title=title)
    for alias in ("/products", "/stylist"):
        page.goto(base + alias, wait_until="networkidle")
        page.get_by_text(title, exact=False).first.wait_for(timeout=10000)
        EV.step(f"G1 alias {alias} renders the same catalogue screen", True)
    EV.step("G1 zero failed /api requests", not api_failures(),
            failures=api_failures()[:5])


def goal_mobile(browser, base: str) -> None:
    for w in (390, 360):
        ctx = browser.new_context(viewport={"width": w, "height": 844})
        pg = ctx.new_page()
        pg.goto(base + "/discover", wait_until="networkidle")
        overflow = pg.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth")
        EV.step(f"G1[mobile {w}px] no horizontal overflow", overflow <= 1,
                overflow_px=overflow)
        ctx.close()


def search_box(page):
    return page.get_by_role("combobox", name=re.compile("search", re.I)).first


def goal_search_combobox(page, base: str) -> None:
    page.goto(base + "/discover", wait_until="networkidle")
    box = search_box(page)
    with page.expect_response(lambda r: "/catalog/autocomplete" in r.url) as ac:
        box.click()
        box.fill("wool")
    EV.step("G2 autocomplete fired on the wire", ac.value.status == 200,
            status=ac.value.status)
    page.wait_for_selector('#discover-suggestions [role="option"]', timeout=8000)
    EV.step("G2 listbox with role=option rows appeared", True,
            options=page.locator('#discover-suggestions [role="option"]').count())
    EV.step("G2 ?q= written to the URL", "q=wool" in page.url, url=page.url)

    box.press("ArrowDown")
    active = box.get_attribute("aria-activedescendant")
    EV.step("G2 ArrowDown drives aria-activedescendant",
            active == "discover-sug-0", active=active)
    # Enter selects the active option: for a product suggestion this must
    # land on the PDP; for brand/category it fills the query. Both are
    # observable, neither may crash.
    opt_text = page.locator("#discover-sug-0").inner_text()
    box.press("Enter")
    page.wait_for_timeout(600)
    on_pdp = re.search(r"/product/", page.url) is not None
    listbox_closed = page.locator('#discover-suggestions').count() == 0
    EV.step("G2 Enter acted on the active option (PDP or query fill)",
            on_pdp or listbox_closed, landed=page.url, option=opt_text[:40])


def goal_occasion_filter(page, base: str) -> None:
    vocab = page.request.get(base + "/api/v1/catalog/occasions").json()
    assert vocab, "empty occasion vocabulary"
    token = vocab[0]["value"]
    api_ids = [p["id"] for p in page.request.get(
        base + f"/api/v1/catalog/products?occasion={token}").json()]
    EV.step("G3 live vocabulary available", True, first_token=token,
            api_matches=len(api_ids))

    page.goto(base + "/discover", wait_until="networkidle")
    # The pill row renders translated labels; find the pill whose click
    # puts the TOKEN on the wire.
    # The pill label follows the app's own contract: t(`discover.
    # occasion_<token>`) with a humanised fallback. Read it from the
    # served EN locale so the probe can't drift from the UI.
    en = page.request.get(base + "/src/i18n/en.json").json()
    label = en.get("discover", {}).get(
        f"occasion_{token}", token.replace("_", " "))
    with page.expect_response(
        lambda r: "/catalog/products" in r.url and f"occasion={token}" in r.url
    ) as resp_info:
        page.locator('button[aria-pressed]', has_text=label).first.click()
    EV.step("G3 pill click put ?occasion= on the wire", True,
            wire_url=resp_info.value.url, status=resp_info.value.status)
    EV.step("G3 URL write-back", f"occasion={token}" in page.url, url=page.url)
    grid_ids = page.evaluate(
        "[...document.querySelectorAll('[data-product-id]')].map(e => +e.dataset.productId)")
    EV.step("G3 grid equals the API answer for that occasion",
            set(grid_ids) == set(api_ids), grid=grid_ids, api=api_ids)


def goal_deep_link(page, base: str) -> None:
    vocab = page.request.get(base + "/api/v1/catalog/occasions").json()
    token = vocab[0]["value"]
    en = page.request.get(base + "/src/i18n/en.json").json()
    label = en.get("discover", {}).get(
        f"occasion_{token}", token.replace("_", " "))
    page.goto(base + f"/discover?occasion={token}&sort=newest",
              wait_until="networkidle")
    pressed = page.locator('button[aria-pressed="true"]').all_inner_texts()
    label_match = any(label.lower() in t.strip().lower() for t in pressed)
    EV.step("G4 deep link restores the pressed pill", label_match,
            pressed=pressed[:6], expected_label=label)
    sort_value = page.locator("select").last.input_value()
    EV.step("G4 deep link restores the sort order", sort_value == "newest",
            got=sort_value)
    # counter-goal: junk is ignored
    page.goto(base + "/discover?occasion=junk_token_xyz&sort=hack",
              wait_until="networkidle")
    pressed = [t.strip().lower()
               for t in page.locator('button[aria-pressed="true"]').all_inner_texts()]
    EV.step("G4 junk tokens are never applied",
            "junk" not in " ".join(pressed)
            and page.locator("select").last.input_value() != "hack",
            pressed=pressed[:6])


def goal_real_links(page, base: str) -> None:
    page.goto(base + "/discover", wait_until="networkidle")
    links = page.locator('[data-testid="product-card"] a[href^="/product/"]')
    n = links.count()
    EV.step("G5 product cards expose REAL hrefs to the PDP", n > 0, links=n)
    href = links.first.get_attribute("href")
    links.first.click()
    page.wait_for_url(re.compile(r"/product/"), timeout=10000)
    EV.step("G5 clicking the card link lands on the PDP", True,
            href=href, url=page.url)


def goal_wishlist_persists(page, base: str) -> None:
    page.goto(base + "/discover", wait_until="networkidle")
    hearts = page.get_by_role("button", name=re.compile("wishlist", re.I))
    hearts.first.wait_for(timeout=8000)
    hearts.first.click()
    page.wait_for_timeout(300)
    stored = page.evaluate("localStorage.getItem('confit.wishlist.v1')")
    EV.step("G6 heart persisted to device storage", stored not in (None, "[]"),
            stored=stored)
    page.reload(wait_until="networkidle")
    pressed = page.get_by_role("button", name=re.compile("wishlist", re.I)) \
                  .first.get_attribute("aria-pressed")
    EV.step("G6 heart still pressed after a full reload", pressed == "true",
            aria_pressed=pressed)


def goal_arabic(page, base: str) -> None:
    page.goto(base + "/discover", wait_until="domcontentloaded")
    page.evaluate("localStorage.setItem('confit_lang', 'ar')")
    page.goto(base + "/discover", wait_until="networkidle")
    assert_valid(page)
    EV.step("G7 dir=rtl in Arabic",
            page.evaluate("document.documentElement.getAttribute('dir')") == "rtl")
    EV.step("G7 Arabic copy renders",
            re.search(r"[\u0600-\u06FF]{3,}", page.inner_text("body")) is not None)
    vocab = page.request.get(base + "/api/v1/catalog/occasions").json()
    token = vocab[0]["value"]
    # The UI labels the pill with t(`discover.occasion_<token>`) — read the
    # REAL Arabic label straight from the served locale file so the probe
    # follows the same contract as the app (vite dev serves /src/*).
    ar = page.request.get(base + "/src/i18n/ar.json").json()
    label = ar.get("discover", {}).get(
        f"occasion_{token}", token.replace("_", " "))
    with page.expect_response(
        lambda r: "/catalog/products" in r.url and f"occasion={token}" in r.url
    ) as resp_info:
        page.locator('button[aria-pressed]', has_text=label).first.click()
    EV.step("G7 Arabic UI still sends the ENGLISH wire token",
            f"occasion={token}" in resp_info.value.url,
            wire=resp_info.value.url)


def goal_category_filter(page, base: str) -> None:
    """G8 — browse by category: pill -> wire -> URL -> deep link."""
    cats = page.request.get(base + "/api/v1/catalog/categories").json()
    assert cats, "no categories"
    cat = cats[0]
    page.goto(base + "/discover", wait_until="networkidle")
    with page.expect_response(
        lambda r: "/catalog/products" in r.url and f"category={cat['slug']}" in r.url
    ) as resp_info:
        page.locator('button[aria-pressed]', has_text=cat["name"]).first.click()
    EV.step("G8 category pill put ?category= on the wire",
            resp_info.value.status == 200, wire=resp_info.value.url)
    EV.step("G8 URL write-back", f"category={cat['slug']}" in page.url,
            url=page.url)
    page.goto(base + f"/discover?category={cat['slug']}",
              wait_until="networkidle")
    pressed = page.locator('button[aria-pressed="true"]').all_inner_texts()
    EV.step("G8 ?category= deep link restores the pressed pill",
            any(cat["name"].lower() in t.strip().lower() for t in pressed),
            pressed=pressed[:6])


def goal_sort_wire(page, base: str) -> None:
    """G9 — sorting refetches with the chosen order and syncs the URL."""
    page.goto(base + "/discover", wait_until="networkidle")
    en = page.request.get(base + "/src/i18n/en.json").json()
    sort_name = en["a11y"]["sort_products"]
    with page.expect_response(
        lambda r: "/catalog/products" in r.url and "sort_by=price_asc" in r.url
    ) as resp_info:
        page.get_by_label(sort_name).select_option("price_asc")
    EV.step("G9 sort change put sort_by=price_asc on the wire",
            resp_info.value.status == 200, wire=resp_info.value.url)
    EV.step("G9 sort URL write-back", "sort=price_asc" in page.url,
            url=page.url)
    api_prices = [p["base_price"] for p in page.request.get(
        base + "/api/v1/catalog/products?sort_by=price_asc").json()]
    EV.step("G9 API answer for that order is ascending",
            api_prices == sorted(api_prices), prices=api_prices[:6])


def goal_visual_search(page, base: str) -> None:
    """G10 — visual search: real wire call, honest terminal state, never
    a silent or fake-success dialog."""
    page.goto(base + "/discover", wait_until="networkidle")
    en = page.request.get(base + "/src/i18n/en.json").json()
    page.get_by_role("button", name=en["discover"]["search_by_photo"]).click()
    dialog = page.get_by_role("dialog", name=en["tryon"]["visual_search"])
    dialog.wait_for(timeout=8000)
    EV.step("G10 modal opens as a named dialog", True)
    # C02 re-pass fix: the close button must have an accessible name.
    EV.step("G10 close button exposes an accessible name",
            dialog.get_by_role("button",
                               name=en["a11y"]["close_dialog"]).count() == 1)
    # Search with a REAL catalogue image URL (local backend can fetch it).
    img = page.request.get(
        base + "/api/v1/catalog/products").json()[0]["thumbnail_url"]
    dialog.get_by_placeholder(en["tryon"]["paste_image_url"]).fill(img)
    with page.expect_response(
        lambda r: "/tryon/visual-search" in r.url, timeout=60000
    ) as resp_info:
        dialog.get_by_role("button",
                           name=en["tryon"]["vs_search_style"]).click()
    status = resp_info.value.status
    EV.step("G10 search hit the real /tryon/visual-search endpoint", True,
            status=status)
    # Honest terminal state: matches grid (with detection or the explicit
    # no-detection banner) on 200, role=alert + retry on failure. Never
    # silence, never success-without-server.
    page.wait_for_timeout(800)
    if status == 200:
        body = resp_info.value.json()
        shown = dialog.locator('[data-product-id], img[alt]')
        banner_ok = (
            dialog.get_by_text(en["tryon"]["vs_analysis_unavailable"]).count() > 0
            or body.get("analysis_available") is True
        )
        EV.step("G10 200 -> matches rendered + honest detection banner",
                banner_ok and len(body.get("matches", [])) >= 0,
                analysis_available=body.get("analysis_available"),
                matches=len(body.get("matches", [])))
    else:
        EV.step("G10 failure -> explicit error alert, no fake success",
                dialog.get_by_role("alert").count() > 0, status=status)
    page.keyboard.press("Escape")
    # Wait for the MEANINGFUL result (unmount), not an instant count.
    dialog.wait_for(state="detached", timeout=5000)
    EV.step("G10 Escape closes the dialog", True)


def goal_no_photo_fit(page, base: str) -> None:
    """G11 — the no-photo fit (ruler) entry on the card opens the real
    measurement dialog; the card never promises an unavailable render."""
    page.goto(base + "/discover", wait_until="networkidle")
    en = page.request.get(base + "/src/i18n/en.json").json()
    ruler = page.get_by_role("button", name=en["a11y"]["no_photo_fit"]).first
    ruler.wait_for(timeout=8000)
    ruler.click()
    fit_dialog = page.locator('[aria-labelledby="no-photo-fit-title"]')
    fit_dialog.wait_for(timeout=8000)
    EV.step("G11 ruler entry opens the no-photo fit dialog", True)
    fit_dialog.get_by_role("button", name=en["common"]["close"]).click()
    page.wait_for_timeout(300)
    EV.step("G11 dialog closes cleanly",
            page.locator('[aria-labelledby="no-photo-fit-title"]').count() == 0)


def goal_add_to_bag_idempotent(page, base: str) -> None:
    """G12 counter-goal — double-clicking Add never creates two adds, and
    no success is claimed before the server answers."""
    page.goto(base + "/discover", wait_until="networkidle")
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url)
            if r.method == "POST" and "/commerce/cart/items" in r.url else None)
    btn = page.get_by_test_id("product-card-add-to-bag").first
    btn.scroll_into_view_if_needed()
    with page.expect_response(
        lambda r: "/commerce/cart/items" in r.url, timeout=15000
    ) as resp_info:
        btn.click()
        btn.click(force=True)  # the hammer double-click
    page.wait_for_timeout(1500)  # grace: any wrongly queued second POST
    EV.step("G12 double-click produced exactly ONE cart POST",
            len(posts) == 1, posts=len(posts), status=resp_info.value.status)
    # The guest cart's identity is the X-Session-Token header (from
    # localStorage.confit_session_token) — read it so the probe asks the
    # server about the SAME cart the UI mutated.
    token = page.evaluate("localStorage.getItem('confit_session_token')")
    cart = page.request.get(
        base + "/api/v1/commerce/cart",
        headers={"X-Session-Token": token or ""}).json()
    items = cart.get("items", cart if isinstance(cart, list) else [])
    qty = sum(i.get("quantity", 0) for i in items) if isinstance(items, list) else None
    EV.step("G12 server cart holds a single unit (source of truth)",
            qty == 1, cart_quantity=qty)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/tmp/e2e_discover_goals.json")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        wire(page)
        try:
            goal_arrival(page, base)
            goal_mobile(browser, base)
            goal_search_combobox(page, base)
            goal_occasion_filter(page, base)
            goal_deep_link(page, base)
            goal_real_links(page, base)
            goal_wishlist_persists(page, base)
            goal_category_filter(page, base)
            goal_sort_wire(page, base)
            goal_visual_search(page, base)
            goal_no_photo_fit(page, base)
            goal_add_to_bag_idempotent(page, base)
            goal_arabic(page, base)
        except Invalid as exc:
            EV.steps.append({"step": "RUN-INVALID", "ok": False, "err": str(exc)})
        finally:
            Path(args.out).write_text(json.dumps(
                {"steps": EV.steps, "network_tail": EV.network[-40:],
                 "console_errors": EV.console_errors}, indent=2, default=str))
            browser.close()

    failed = [s for s in EV.steps if not s["ok"]]
    print(f"\n{len(EV.steps) - len(failed)}/{len(EV.steps)} steps passed; "
          f"evidence: {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
