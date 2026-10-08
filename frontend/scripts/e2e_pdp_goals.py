#!/usr/bin/env python3
"""Local browser Goal-E2E — the C03 product detail page, EN + AR.

House harness pattern (e2e_home_goals.py / e2e_discover_goals.py): every
goal is proven UI action -> HTTP -> server truth -> UI state, with the
network evidence kept in the output. A half-rendered page is a
measurement failure, never a pass.

Goals (visitor role):
  G1  Arrival by slug: the REAL product (title, formatted price, one
      size button per SKU) renders; the /products/:slug alias shows the
      same page; zero failed /api requests; zero console errors.
  G2  Variants: size buttons mirror SKU truth — selected has
      aria-pressed, out-of-stock ones are disabled.
  G3  Counter-goal: double-clicking Add to bag produces exactly ONE
      cart POST and the SERVER cart holds one unit.
  G4  One wishlist: the PDP heart persists to confit.wishlist.v1,
      survives reload, AND the same product's card on /discover shows
      pressed — one device list across surfaces.
  G5  Breadcrumb truth: the category crumb carries ?category=<slug> and
      landing on it shows the pressed category pill on Discover.
  G6  No-photo fit: the fit CTA opens the real measurement dialog
      (engine offline locally — the page must offer fit-check, never a
      try-on promise it cannot keep).
  G7  BOPIS honesty: the pickup accordion's terminal state matches the
      API answer for the selected SKU (stores listed / none / error).
  G8  Arabic RTL + 390/360px: dir=rtl, Arabic copy, no horizontal
      overflow; pass-2 pin: accordion headers follow the writing
      direction (the text-left regression rendered LTR alignment
      inside the Arabic page).
  G9  Pass 2 — perceived performance: while the detail API is held
      open the page shows the geometry-matched skeleton (role=status),
      and the skeleton leaves when the data lands. The route is HELD
      and released by the test — no timing guesswork.
  G10 Pass 2 — mobile sticky buy bar: on 390px the bar exists while
      the real CTA block is below the fold; a double-tap on its Add
      button produces exactly ONE cart POST and ONE server unit
      (cross-button single-flight guard); reaching the real CTA
      removes the bar (no duplicate pinned control on screen).
  G11 Pass 3 — network dropout: with the connection cut the page
      names the offline state honestly (never the generic server
      error), and when the connection returns it recovers BY ITSELF —
      zero taps — via the browser 'online' event.
  G12 Pass 4 — tab identity + structured data: document.title carries
      the PRODUCT name (not the discover route meta), resets to the
      route title after navigating away, and a valid schema.org
      Product JSON-LD matching the API payload sits in <head>.
  G13 Pass 4 — contextual zoom: clicking a point on the hero zooms at
      THAT point (transform-origin from the click), aria-pressed
      mirrors the state, Escape rests it.
  G14 Pass 4 — browse memory: after visiting product A, product B's
      page shows A in the recently-viewed rail; the card links back
      to A's live page; A never lists itself.
  G15 Card integrity (card-clarity pass) — geometric proof on
      desktop+mobile, EN+AR RTL: no element escapes its card's box,
      no card clips its own content, and every product name in the
      look/recently-viewed cards renders in FULL (the 2-line clamp
      never actually cuts a current catalogue name).

Usage:
    python3 scripts/e2e_pdp_goals.py [--base-url http://127.0.0.1:43123]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

MIN_RENDERED_TEXT = 400


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


def pick_product(page, base: str) -> dict:
    """A seeded product with at least one in-stock SKU."""
    for p in page.request.get(base + "/api/v1/catalog/products").json():
        detail = page.request.get(
            base + f"/api/v1/catalog/products/{p['slug']}").json()
        if any(s["is_in_stock"] for s in detail.get("skus", [])):
            return detail
    raise Invalid("no in-stock seeded product")


def goal_arrival(page, base: str, detail: dict, en: dict) -> None:
    for path in (f"/product/{detail['slug']}", f"/products/{detail['slug']}"):
        page.goto(base + path, wait_until="networkidle")
        page.get_by_role("heading", name=detail["title"]).first.wait_for(
            timeout=10000)
        if len(page.inner_text("body")) < MIN_RENDERED_TEXT:
            raise Invalid(f"{path} under-rendered")
        EV.step(f"G1 {path} renders the real product", True)
    size_group = page.get_by_role("group", name=en["a11y"]["select_size"])
    sizes_ui = size_group.get_by_role("button")
    EV.step("G1 one size control per SKU",
            sizes_ui.count() == len(detail["skus"]),
            ui=sizes_ui.count(), api=len(detail["skus"]))
    EV.step("G1 zero failed /api requests", not api_failures(),
            failures=api_failures()[:5])
    EV.step("G1 zero console errors", not EV.console_errors,
            errors=EV.console_errors[:3])
    # Pass 2: the hero IS the LCP element — it must be requested eagerly
    # with high priority, not lazily like the thumbnails.
    hero = page.locator('img[fetchpriority="high"]').first
    EV.step("G1 hero image carries LCP priority (eager + fetchpriority=high)",
            hero.count() >= 1 and hero.get_attribute("loading") == "eager",
            loading=hero.get_attribute("loading") if hero.count() else None)


def goal_variants(page, base: str, detail: dict, en: dict) -> None:
    group = page.get_by_role("group", name=en["a11y"]["select_size"])
    for sku in detail["skus"]:
        btn = group.get_by_role("button", name=sku["size"], exact=True).first
        disabled = btn.is_disabled()
        if sku["is_in_stock"]:
            EV.step(f"G2 in-stock size {sku['size']} is clickable",
                    not disabled)
            btn.click()
            EV.step(f"G2 selecting {sku['size']} reflects aria-pressed",
                    btn.get_attribute("aria-pressed") == "true")
        else:
            EV.step(f"G2 out-of-stock size {sku['size']} is disabled",
                    disabled)


def goal_add_to_bag(page, base: str, detail: dict) -> None:
    page.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url)
            if r.method == "POST" and "/commerce/cart/items" in r.url else None)
    btn = page.get_by_test_id("pdp-add-to-bag")
    btn.scroll_into_view_if_needed()
    # Pass 2: one synchronous burst (same rationale as G10) — two
    # protocol clicks can straddle a fast local response, turning the
    # counter-goal into a legitimate second add.
    with page.expect_response(
        lambda r: "/commerce/cart/items" in r.url, timeout=15000
    ) as resp_info:
        btn.evaluate("b => { b.click(); b.click(); }")
    page.wait_for_timeout(1500)
    EV.step("G3 double-click produced exactly ONE cart POST",
            len(posts) == 1, posts=len(posts), status=resp_info.value.status)
    token = page.evaluate("localStorage.getItem('confit_session_token')")
    cart = page.request.get(
        base + "/api/v1/commerce/cart",
        headers={"X-Session-Token": token or ""}).json()
    qty = sum(i.get("quantity", 0) for i in cart.get("items", []))
    EV.step("G3 server cart holds a single unit", qty == 1, qty=qty)


def goal_wishlist_cross_surface(page, base: str, detail: dict, en: dict) -> None:
    page.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    heart = page.get_by_role("button", name=en["a11y"]["toggle_wishlist"]).first
    heart.click()
    page.wait_for_timeout(300)
    stored = json.loads(page.evaluate(
        "localStorage.getItem('confit.wishlist.v1') || '[]'"))
    EV.step("G4 heart persisted the product id to the device list",
            detail["id"] in stored, stored=stored)
    page.reload(wait_until="networkidle")
    EV.step("G4 heart still pressed after reload",
            page.get_by_role("button", name=en["a11y"]["toggle_wishlist"])
                .first.get_attribute("aria-pressed") == "true")
    # Cross-surface: the SAME product's grid card on /discover is pressed.
    page.goto(base + "/discover", wait_until="networkidle")
    card = page.locator(f'[data-product-id="{detail["id"]}"]').first
    card.scroll_into_view_if_needed()
    pressed = card.get_by_role(
        "button", name=en["a11y"]["toggle_wishlist"]).get_attribute("aria-pressed")
    EV.step("G4 the same heart is pressed on the Discover grid (one list)",
            pressed == "true", pressed=pressed)


def goal_breadcrumb(page, base: str, detail: dict) -> None:
    page.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    crumb = page.get_by_role("link", name=detail["category_name"]).first
    href = crumb.get_attribute("href")
    EV.step("G5 crumb href carries the category SLUG",
            href == f"/discover?category={detail['category_slug']}", href=href)
    crumb.click()
    page.wait_for_url(re.compile(r"/discover"), timeout=10000)
    page.wait_for_timeout(800)
    pressed = [t.strip().lower() for t in
               page.locator('button[aria-pressed="true"]').all_inner_texts()]
    EV.step("G5 Discover lands with the category pill pressed",
            any(detail["category_name"].lower() in t for t in pressed),
            pressed=pressed[:6])


def goal_fit_check(page, base: str, detail: dict, en: dict) -> None:
    page.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    # HONESTY: the main CTA's label must mirror the LIVE engine verdict —
    # "Try On" only when the engine reports it can render, the fit-check
    # wording otherwise. Read the same source of truth the page reads.
    caps = page.request.get(base + "/api/v1/try-on/capabilities").json()
    render_live = caps.get("engine_state") == "available"
    expected = (en["tryon"]["cta_try_on"] if render_live
                else en["tryon"]["cta_fit_check_instead"])
    cta = page.get_by_role("button", name=expected).last
    cta.scroll_into_view_if_needed()
    EV.step("G6 CTA label mirrors the live engine verdict", cta.count() >= 1,
            engine_state=caps.get("engine_state"), label=expected)
    # The SIZE-SUGGESTION entry ("Find my size") always opens the real
    # measurement dialog, whatever the engine says.
    page.get_by_role("button", name=en["product"]["find_my_size"]).click()
    dialog = page.locator('[aria-labelledby="no-photo-fit-title"]')
    dialog.wait_for(timeout=8000)
    EV.step("G6 find-my-size opens the real measurement dialog", True)
    page.keyboard.press("Escape")
    dialog.wait_for(state="detached", timeout=5000)
    EV.step("G6 Escape closes the measurement dialog", True)


def goal_bopis_truth(page, base: str, detail: dict, en: dict) -> None:
    page.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    first_sku = next(s for s in detail["skus"] if s["is_in_stock"])
    api_stores = page.request.get(
        base + f"/api/v1/catalog/skus/{first_sku['id']}/stores").json()
    pickup = [s for s in api_stores if s.get("is_available_for_pickup")]
    page.get_by_role("button", name=en["product"]["bopis_title"]).click()
    page.wait_for_timeout(1200)
    if pickup:
        shown = page.get_by_text(pickup[0]["store_name"]).count()
        EV.step("G7 accordion lists the stores the API reports",
                shown > 0, api_stores=len(pickup))
    else:
        empty_txt = (en["product"]["bopis_no_store"]
                     if not api_stores else en["product"]["bopis_no_store_stock"])
        EV.step("G7 accordion states the honest empty answer",
                page.get_by_text(empty_txt).count() > 0,
                api_stores=len(api_stores))


def goal_arabic_mobile(page, browser, base: str, detail: dict, ar: dict) -> None:
    page.goto(base + f"/product/{detail['slug']}", wait_until="domcontentloaded")
    page.evaluate("localStorage.setItem('confit_lang','ar')")
    page.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    EV.step("G8 dir=rtl in Arabic",
            page.evaluate("document.documentElement.getAttribute('dir')") == "rtl")
    EV.step("G8 Arabic copy renders",
            re.search(r"[\u0600-\u06FF]{3,}", page.inner_text("body")) is not None)
    # Pass-2 pin: every accordion header follows the writing direction.
    # The shipped text-left class computed to literal "left" in RTL.
    for key in ("fabric_care_details", "bopis_title", "delivery_returns"):
        btn = page.get_by_role("button", name=ar["product"][key]).first
        align = btn.evaluate("e => getComputedStyle(e).textAlign")
        EV.step(f"G8 '{key}' header follows RTL writing direction",
                align != "left", align=align)
    for w in (390, 360):
        ctx = browser.new_context(viewport={"width": w, "height": 844})
        pg = ctx.new_page()
        pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
        overflow = pg.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth")
        EV.step(f"G8[mobile {w}px] no horizontal overflow", overflow <= 1,
                overflow_px=overflow)
        ctx.close()


def goal_skeleton(browser, base: str, detail: dict) -> None:
    """G9: hold the detail API open; the page must show the page-shaped
    skeleton (an accessible status), then swap to the product when the
    route is released. Deterministic — no sleeps inside the handler."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    held: dict = {}
    pg.route(f"**/catalog/products/{detail['slug']}",
             lambda route: held.setdefault("route", route))
    pg.goto(base + f"/product/{detail['slug']}", wait_until="domcontentloaded")
    skeleton = pg.get_by_test_id("pdp-skeleton")
    skeleton.wait_for(timeout=8000)
    EV.step("G9 held API shows the page-shaped skeleton", True)
    EV.step("G9 skeleton is an accessible status",
            skeleton.get_attribute("role") == "status"
            and bool(skeleton.get_attribute("aria-label")),
            role=skeleton.get_attribute("role"))
    if "route" not in held:
        raise Invalid("detail request never reached the held route")
    held["route"].continue_()
    pg.get_by_role("heading", name=detail["title"]).first.wait_for(timeout=10000)
    skeleton.wait_for(state="detached", timeout=5000)
    EV.step("G9 skeleton leaves when the data lands", True)
    pg.unroute(f"**/catalog/products/{detail['slug']}")
    ctx.close()


def goal_sticky_bar(browser, base: str, detail: dict) -> None:
    """G10: mobile sticky buy bar — present only while the real CTA block
    is off screen, single-flight across its Add button, gone once the
    real CTA is reached."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    posts: list[str] = []
    pg.on("request", lambda r: posts.append(r.url)
          if r.method == "POST" and "/commerce/cart/items" in r.url else None)
    pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    bar = pg.get_by_test_id("pdp-sticky-bar")
    bar.wait_for(timeout=8000)
    EV.step("G10 bar present while the real CTA is below the fold", True)
    btn = pg.get_by_test_id("pdp-add-to-bag-sticky")
    # Double-tap as ONE synchronous burst. Two separate protocol clicks
    # are racy against a fast local server: the second can land AFTER
    # the first response, which is a legitimate second add, not a
    # double-submit (observed flake: posts=2). Two clicks in the same
    # JS tick make it impossible for the response to sit between them —
    # exactly the burst the single-flight guard exists for. (A plain
    # second force-click was worse: the success flow opens the cart
    # drawer and the forced click hit the drawer's checkout control.)
    with pg.expect_response(
        lambda r: "/commerce/cart/items" in r.url, timeout=15000
    ) as resp_info:
        btn.evaluate("b => { b.click(); b.click(); }")
    pg.wait_for_timeout(1500)
    EV.step("G10 double-tap on the bar produced exactly ONE cart POST",
            len(posts) == 1, posts=len(posts), status=resp_info.value.status)
    token = pg.evaluate("localStorage.getItem('confit_session_token')")
    cart = pg.request.get(
        base + "/api/v1/commerce/cart",
        headers={"X-Session-Token": token or ""}).json()
    qty = sum(i.get("quantity", 0) for i in cart.get("items", []))
    EV.step("G10 server cart holds a single unit", qty == 1, qty=qty)
    # Fresh load (closes the drawer the success opened), then reach the
    # real CTA: the bar must leave — no duplicate pinned control.
    pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    bar.wait_for(timeout=8000)
    pg.get_by_test_id("pdp-add-to-bag").scroll_into_view_if_needed()
    bar.wait_for(state="detached", timeout=5000)
    EV.step("G10 bar leaves once the real CTA is on screen", True)
    ctx.close()


def goal_offline_recovery(browser, base: str, detail: dict, en: dict) -> None:
    """G11: cut the network, navigate client-side to the product, see the
    honest offline story; restore the network and watch the page recover
    with ZERO user action."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    # Warm the route module once so the SPA navigation below needs no
    # network for code — only the API call will fail offline.
    pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    pg.goto(base + "/discover", wait_until="networkidle")
    ctx.set_offline(True)
    link = pg.locator(f'a[href="/product/{detail["slug"]}"]').first
    link.click()
    offline_copy = pg.get_by_text(en["product"]["offline_desc"])
    offline_copy.wait_for(timeout=10000)
    EV.step("G11 dropout shows the honest offline story", True)
    EV.step("G11 offline never claims a server error",
            pg.get_by_text(en["product"]["load_failed_desc"]).count() == 0)
    ctx.set_offline(False)
    # No clicks from here: the 'online' listener must refetch alone.
    pg.get_by_role("heading", name=detail["title"]).first.wait_for(
        timeout=10000)
    offline_copy.wait_for(state="detached", timeout=5000)
    EV.step("G11 connection back -> page recovers with ZERO taps", True)
    ctx.close()


def goal_tab_identity(browser, base: str, detail: dict, en: dict) -> None:
    """G12: the tab names the product; leaving resets it; JSON-LD valid."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    pg.get_by_role("heading", name=detail["title"]).first.wait_for(timeout=10000)
    title = pg.title()
    EV.step("G12 tab carries the PRODUCT name",
            title == f"{detail['title']} · CONFIT", title=title)
    ld = pg.locator('script[data-testid="pdp-jsonld"]')
    EV.step("G12 one JSON-LD block in head", ld.count() == 1)
    data = json.loads(ld.first.text_content() or "{}")
    EV.step("G12 JSON-LD mirrors the API payload",
            data.get("@type") == "Product"
            and data.get("name") == detail["title"]
            and data.get("offers", {}).get("price") == detail["base_price"],
            ld_name=data.get("name"))
    # Navigating away: the override must not leak.
    pg.get_by_role("link", name=en["product"]["breadcrumb_catalog"]).first.click()
    pg.wait_for_url(re.compile(r"/discover"), timeout=10000)
    pg.wait_for_timeout(400)
    after = pg.title()
    EV.step("G12 next page gets its OWN title back",
            detail["title"] not in after, title=after)
    ctx.close()


def goal_contextual_zoom(browser, base: str, detail: dict) -> None:
    """G13: zoom happens AT the clicked point and rests on Escape."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    toggle = pg.get_by_test_id("pdp-zoom-toggle")
    box = toggle.bounding_box()
    # Click the upper-start quarter — origin must land near 25%/25%.
    toggle.click(position={"x": box["width"] * 0.25, "y": box["height"] * 0.25})
    EV.step("G13 zoom toggle reports pressed",
            toggle.get_attribute("aria-pressed") == "true")
    hero = pg.locator(f'img[alt="{detail["title"]}"]').first
    origin = hero.evaluate("e => e.style.transformOrigin")
    ox = float(origin.split("%")[0])
    EV.step("G13 transform-origin follows the clicked point",
            10 <= ox <= 40, origin=origin)
    # The zoom rides a 700ms luxury transition — wait for it to SETTLE
    # instead of sampling the first interpolated frame (first run read
    # matrix(1,...) immediately after the click).
    pg.wait_for_function(
        """() => {
            const img = document.querySelector('img[fetchpriority="high"]');
            return img && getComputedStyle(img).transform.startsWith('matrix(2');
        }""",
        timeout=5000,
    )
    EV.step("G13 the photograph actually scales to 2x", True)
    toggle.focus()
    pg.keyboard.press("Escape")
    EV.step("G13 Escape rests the zoom",
            toggle.get_attribute("aria-pressed") == "false"
            and hero.evaluate("e => e.style.transformOrigin") == "")
    ctx.close()


def goal_browse_memory(page, browser, base: str, detail: dict, en: dict) -> None:
    """G14: visit A, then B — B's rail shows A and links back to A."""
    products = page.request.get(base + "/api/v1/catalog/products").json()
    other = next(p for p in products if p["slug"] != detail["slug"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
    pg.get_by_role("heading", name=detail["title"]).first.wait_for(timeout=10000)
    EV.step("G14 product A never lists itself",
            pg.get_by_test_id("pdp-recently-viewed").count() == 0)
    pg.goto(base + f"/product/{other['slug']}", wait_until="networkidle")
    rail = pg.get_by_test_id("pdp-recently-viewed")
    rail.wait_for(timeout=8000)
    card = rail.locator(f'a[href="/product/{detail["slug"]}"]').first
    EV.step("G14 product B's rail shows A", card.count() == 1)
    card.click()
    pg.get_by_role("heading", name=detail["title"]).first.wait_for(timeout=10000)
    EV.step("G14 the card leads back to A's live page", True)
    ctx.close()


CARD_AUDIT_JS = """
() => {
  const cards = [...document.querySelectorAll(
    '.surface-solid, .surface-raised, .surface-glass-light, .surface-glass-dark'
  )];
  const issues = [];
  for (const card of cards) {
    const cr = card.getBoundingClientRect();
    if (cr.width === 0 || cr.height === 0) continue;
    for (const el of card.querySelectorAll('*')) {
      const st = getComputedStyle(el);
      if (st.position === 'fixed' || st.display === 'none' || st.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const worst = Math.max(cr.top - r.top, r.bottom - cr.bottom,
                             cr.left - r.left, r.right - cr.right);
      if (worst > 1.5) issues.push('escape:' + (el.textContent || '').trim().slice(0, 40));
    }
    if (card.scrollHeight > card.clientHeight + 2 &&
        getComputedStyle(card).overflowY !== 'visible')
      issues.push('card-clips-content');
  }
  // Product names in look/rail cards must never be line-clamped or
  // vertically cut — the full name is the contract.
  for (const el of document.querySelectorAll('[class*="line-clamp"]')) {
    if (el.closest('[data-testid="pdp-recently-viewed"]') || el.closest('section'))
      if (el.scrollHeight > el.clientHeight + 2)
        issues.push('name-cut:' + (el.textContent || '').trim().slice(0, 40));
  }
  // Nothing may still single-line-truncate a product name inside a card.
  for (const el of document.querySelectorAll(
      '[data-testid="pdp-recently-viewed"] .truncate, section .truncate')) {
    if (el.closest('[data-testid="pdp-sticky-bar"]')) continue;  // bar, not a card
    if (el.closest('nav')) continue;                              // breadcrumb
    if (el.scrollWidth > el.clientWidth + 2)
      issues.push('truncated:' + (el.textContent || '').trim().slice(0, 40));
  }
  return issues;
}
"""


def goal_card_integrity(browser, base: str, detail: dict, other_slug: str) -> None:
    """G15: geometric card audit — desktop+mobile, EN+AR."""
    for label, vp, lang in (
        ("desktop-en", (1355, 900), "en"),
        ("mobile-en", (390, 844), "en"),
        ("desktop-ar", (1355, 900), "ar"),
        ("mobile-ar", (390, 844), "ar"),
    ):
        ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]})
        pg = ctx.new_page()
        pg.goto(base, wait_until="domcontentloaded")
        pg.evaluate(f"localStorage.setItem('confit_lang','{lang}')")
        # Seed browse history so the recently-viewed rail is part of the audit.
        pg.goto(base + f"/product/{other_slug}", wait_until="networkidle")
        pg.goto(base + f"/product/{detail['slug']}", wait_until="networkidle")
        pg.wait_for_timeout(1200)  # reveal animations settle
        issues = pg.evaluate(CARD_AUDIT_JS)
        EV.step(f"G15 {label}: every card holds its content, no name cut",
                len(issues) == 0, issues=issues[:8])
        ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/tmp/e2e_pdp_goals.json")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        wire(page)
        try:
            en = page.request.get(base + "/src/i18n/en.json").json()
            ar = page.request.get(base + "/src/i18n/ar.json").json()
            detail = pick_product(page, base)
            goal_arrival(page, base, detail, en)
            goal_variants(page, base, detail, en)
            goal_add_to_bag(page, base, detail)
            goal_wishlist_cross_surface(page, base, detail, en)
            goal_breadcrumb(page, base, detail)
            goal_fit_check(page, base, detail, en)
            goal_bopis_truth(page, base, detail, en)
            goal_arabic_mobile(page, browser, base, detail, ar)
            goal_skeleton(browser, base, detail)
            goal_sticky_bar(browser, base, detail)
            goal_offline_recovery(browser, base, detail, en)
            goal_tab_identity(browser, base, detail, en)
            goal_contextual_zoom(browser, base, detail)
            goal_browse_memory(page, browser, base, detail, en)
            products = page.request.get(base + "/api/v1/catalog/products").json()
            other_slug = next(p["slug"] for p in products if p["slug"] != detail["slug"])
            goal_card_integrity(browser, base, detail, other_slug)
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
