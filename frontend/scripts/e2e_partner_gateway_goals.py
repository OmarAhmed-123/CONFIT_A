#!/usr/bin/env python3
"""Local browser Goal-E2E — the B01 public partner gateway, EN + AR.

House harness pattern (e2e_home_goals.py / e2e_pdp_goals.py): every goal is
proven UI action -> HTTP -> server truth -> UI state, with the network
evidence kept in the output. A half-rendered page is a measurement failure,
never a pass.

Role under test: VISITOR — no partner session, no customer account. B01 is
`/b2b` reached with no partner credentials, and it must never be confused
with shopper account creation: this page collects a partnership lead, it
does not register a customer.

Goals:
  G1  Arrival: the gateway renders its full contract (masthead, the four
      service pillars, the lead form with all six fields, the FAQ, the
      close), with zero failed /api requests and zero console errors.
  G2  Not customer sign-up: the page never offers shopper registration and
      the partnership submit is a distinct control from partner sign-in.
  G3  Client validation is free: submitting with empty required fields
      makes ZERO requests to the lead endpoint and marks the offending
      fields with aria-invalid + an accessible description.
  G4  Happy path with server truth: a complete, valid submission produces
      exactly ONE POST, a 201, and the returned lead id is rendered back
      as the CONFIT-<id> reference. Re-submitting the same address through
      the API returns duplicate=true — proof the row is really persisted,
      not merely acknowledged by the UI.
  G5  Counter-goal: double-clicking submit produces exactly ONE POST, so a
      nervous prospect cannot create two leads.
  G6  Throttle: once the ceiling is hit the page says so in its own voice
      (never the generic server error), offers email instead of retry, and
      keeps the typed values.
  G7  Server 422 renders as FIELD errors, not a generic failure. Simulated
      with a route stub because the client validates the same rules first,
      so a real 422 is not reachable from honest UI input.
  G8  Network dropout: with the request aborted the page names the offline
      state, never shows success, and keeps the typed values.
  G9  Arabic RTL: dir=rtl, Arabic copy, and the same form contract holds.
  G10 Responsive: 390px has no horizontal overflow and the form is
      reachable and operable.
  G11 Keyboard: the masthead CTA moves focus into the form, and the submit
      is operable by keyboard alone.

Usage:
    # Phase 1 — everything except the throttle goal (uses <= 3 lead POSTs)
    python3 scripts/e2e_partner_gateway_goals.py --phase main

    # Phase 2 — the throttle goal alone (needs a fresh limiter window)
    python3 scripts/e2e_partner_gateway_goals.py --phase throttle

    # Both, when the API has just been restarted
    python3 scripts/e2e_partner_gateway_goals.py --phase all

The lead endpoint is limited to 5 requests/hour per network (both by the
slowapi route limit and by the service ceiling). `--phase` exists because a
single run cannot honestly exercise the ceiling AND the success paths
inside one five-request budget. Restarting the API resets the in-process
limiter counters; the service ceiling counts audit rows, so
scripts/clean_e2e_test_data.py (or a direct delete of action IN
('partner_request_demo','partner_lead_notification')) resets that one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# This is a focused page, not a catalogue grid: the render floor is lower than
# the home/PDP harnesses, and the real render proof is the field contract in
# G1 rather than a character count alone.
MIN_RENDERED_TEXT = 900

LEAD_ENDPOINT = "/request-demo"

FIELDS = {
    "company": "Company name",
    "contact": "Contact name",
    "email": "Work email",
    "website": "Website (optional)",
    "volume": "Monthly online orders",
    "message": "What would you like to evaluate?",
}

REQUIRED = ("company", "contact", "email")


class Invalid(Exception):
    """The measurement itself is not trustworthy — never treated as a pass."""


class Evidence:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.network: list[dict] = []
        self.console_errors: list[str] = []
        self.created_emails: list[str] = []

    def step(self, name: str, ok: bool, **detail) -> None:
        self.steps.append({"step": name, "ok": ok, **detail})
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        if not ok:
            raise Invalid(name + ": " + json.dumps(detail, default=str)[:500])


EV = Evidence()


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------

def wire_network(page) -> None:
    def on_response(resp):
        if "/api/" in resp.url:
            EV.network.append({
                "url": resp.url, "status": resp.status,
                "method": resp.request.method,
            })

    page.on("response", on_response)
    page.on("pageerror", lambda e: EV.console_errors.append(str(e)))
    page.on(
        "console",
        lambda m: EV.console_errors.append(m.text) if m.type == "error" else None,
    )


def api_failures(allow_429: bool = False) -> list[dict]:
    """4xx/5xx on /api that this page did not earn."""
    out = []
    for n in EV.network:
        if n["status"] < 400:
            continue
        if allow_429 and n["status"] == 429 and LEAD_ENDPOINT in n["url"]:
            continue  # the throttle goal provokes this on purpose
        out.append(n)
    return out


def assert_valid_render(page) -> None:
    body = page.inner_text("body")
    if len(body) < MIN_RENDERED_TEXT:
        raise Invalid(f"page under-rendered: {len(body)} chars")
    if EV.console_errors:
        raise Invalid("console/page errors: " + "; ".join(EV.console_errors[:3]))


def lead_posts() -> list[dict]:
    return [n for n in EV.network
            if n["method"] == "POST" and LEAD_ENDPOINT in n["url"]]


def field(page, key: str):
    """The control by its accessible name — never by CSS class or position."""
    name = FIELDS[key]
    # The volume control is a <select>; the rest are inputs. Ask for either by
    # role so the query stays semantic and layout-independent.
    for role in ("textbox", "combobox"):
        loc = page.get_by_role(role, name=re.compile(re.escape(name), re.I))
        if loc.count():
            return loc.first
    raise Invalid(f"no accessible control named {name!r}")


def fill_valid(page, email: str) -> None:
    field(page, "company").fill("E2E Verification Brand")
    field(page, "contact").fill("Goal E2E Contact")
    field(page, "email").fill(email)
    field(page, "website").fill("https://e2e-example.test")
    field(page, "message").fill("Goal-oriented E2E verification — safe to discard.")


def submit_button(page):
    return page.get_by_role("button",
                            name=re.compile(r"request partnership review", re.I)).first


def unique_email(tag: str) -> str:
    email = f"e2e-{tag}-{int(time.time() * 1000) % 10_000_000}@confit-e2e.test"
    EV.created_emails.append(email)
    return email


def submit_and_capture(page, timeout_ms: int = 20_000):
    """Click submit and return the lead POST response — no fixed sleeps."""
    with page.expect_response(
        lambda r: LEAD_ENDPOINT in r.url and r.request.method == "POST",
        timeout=timeout_ms,
    ) as info:
        submit_button(page).click()
    return info.value


# --------------------------------------------------------------------------
# Goals
# --------------------------------------------------------------------------

def goal_arrival(page, base: str) -> None:
    page.goto(base + "/b2b", wait_until="networkidle")
    assert_valid_render(page)
    EV.step("G1 gateway rendered with real content", True,
            text_chars=len(page.inner_text("body")))

    missing = [k for k in FIELDS if field(page, k).count() == 0]
    EV.step("G1 all six lead fields are present and accessible", not missing,
            missing=missing)

    body = page.inner_text("body")
    pillars = ["Catalog ingestion", "Fit intelligence",
               "Virtual try-on", "Operational clarity"]
    absent = [p for p in pillars if p not in body]
    EV.step("G1 the service definition (four pillars) is stated, not just a form",
            not absent, absent=absent)

    EV.step("G1 the form heading is present",
            "Request a partner demo" in body)
    EV.step("G1 no failed /api requests on arrival", not api_failures(),
            failures=api_failures()[:5])


def goal_not_customer_signup(page) -> None:
    body = page.inner_text("body")
    shopper_registration = [
        "create new account", "create an account", "sign up", "register",
        "create your account",
    ]
    hits = [s for s in shopper_registration if s in body.lower()]
    EV.step("G2 the gateway offers no shopper registration", not hits, hits=hits)

    signin = page.get_by_role("button",
                              name=re.compile(r"existing partner sign in", re.I)).first
    submit = submit_button(page)
    EV.step("G2 both the partner sign-in and the partnership submit exist",
            signin.count() > 0 and submit.count() > 0)

    # Distinctness that means something: the sign-in is NOT part of the lead
    # form, so it can never be mistaken for the submit, and the submit lives
    # inside a real <form> — a lead capture, not a navigation affordance.
    signin_in_form = signin.evaluate("el => !!el.closest('form')")
    submit_in_form = submit.evaluate("el => !!el.closest('form')")
    EV.step("G2 the sign-in sits outside the lead form; the submit is inside one",
            signin_in_form is False and submit_in_form is True,
            signin_in_form=signin_in_form, submit_in_form=submit_in_form)

    # Goal, not structure: a partner who ALREADY has an account must actually
    # reach sign-in from here — and land on sign-in, not on registration.
    signin.click()
    dialog = page.get_by_role("dialog")
    EV.step("G2 the sign-in control opens a real dialog",
            dialog.count() > 0 and dialog.first.is_visible())
    EV.step("G2 the dialog opens in SIGN-IN mode, not registration",
            dialog.first.get_by_role("textbox", name=re.compile(r"email", re.I)).count() > 0
            and dialog.first.locator("input[type='password']").count() > 0)
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('[role=\"dialog\"]')",
                           timeout=10_000)
    EV.step("G2 the dialog closes and leaves the gateway intact",
            field(page, "company").count() > 0)


def goal_client_validation_is_free(page, base: str) -> None:
    page.goto(base + "/b2b", wait_until="networkidle")
    before = len(lead_posts())
    submit_button(page).click()

    # Zero requests is the whole point: an invalid submit must not spend the
    # visitor's five-request hourly budget on a request that cannot succeed.
    page.wait_for_timeout(300)  # give any erroneous request time to appear
    made = len(lead_posts()) - before
    EV.step("G3 an invalid submit makes ZERO network requests", made == 0,
            requests_made=made)

    invalid = [k for k in REQUIRED
               if field(page, k).get_attribute("aria-invalid") == "true"]
    EV.step("G3 every required field is marked aria-invalid", len(invalid) == 3,
            marked=invalid)

    described = [k for k in REQUIRED if field(page, k).get_attribute("aria-describedby")]
    EV.step("G3 each invalid field points at an accessible description",
            len(described) == 3, described=described)

    body = page.inner_text("body")
    EV.step("G3 the validation message is specific, not generic",
            "Enter at least 2 characters." in body
            and "Enter a valid work email address." in body)


def goal_happy_path(page, base: str, ctx) -> None:
    page.goto(base + "/b2b", wait_until="networkidle")
    email = unique_email("happy")
    fill_valid(page, email)
    before = len(lead_posts())

    resp = submit_and_capture(page)
    EV.step("G4 the submit produced exactly ONE POST", len(lead_posts()) - before == 1,
            posts=len(lead_posts()) - before)
    EV.step("G4 the server answered 201", resp.status == 201, status=resp.status,
            body=resp.text()[:200])

    payload = resp.json()
    lead_id = payload.get("id")
    EV.step("G4 the server returned a lead id", isinstance(lead_id, int), id=lead_id)

    ref = page.get_by_text(re.compile(rf"CONFIT-{lead_id}\b"))
    EV.step("G4 the returned id is rendered back as CONFIT-<id>", ref.count() > 0,
            expected=f"CONFIT-{lead_id}")
    EV.step("G4 success copy is shown", "Request received." in page.inner_text("body"))

    # SERVER TRUTH, not UI trust: the same address submitted straight to the
    # API must come back as a duplicate. That is only possible if the row the
    # UI celebrated actually exists.
    again = ctx.request.post(base + "/api/v1/brand/request-demo", data={
        "company_name": "E2E Verification Brand",
        "contact_name": "Goal E2E Contact",
        "work_email": email,
    })
    ok = again.status in (200, 201)
    dup = again.json().get("duplicate") if ok else None
    EV.step("G4 the lead is really persisted server-side (resubmit => duplicate)",
            ok and dup is True, status=again.status, duplicate=dup)

    # Values survive a successful submit so a second look is not a retype.
    EV.step("G4 the typed company name is still on screen",
            field(page, "company").input_value() == "E2E Verification Brand")


def goal_double_click_single_lead(page, base: str) -> None:
    page.goto(base + "/b2b", wait_until="networkidle")
    email = unique_email("dbl")
    fill_valid(page, email)
    before = len(lead_posts())

    # Two Playwright click() calls are separate round-trips (measured here at
    # ~54ms apart) while the local API answers in 17-41ms, so spaced clicks do
    # not overlap the in-flight window at all. Firing both clicks inside ONE
    # browser task makes them genuinely concurrent. The button is still located
    # semantically; evaluate is used only to dispatch.
    submit_button(page).evaluate("el => { el.click(); el.click(); }")

    page.wait_for_function(
        """() => {
             const t = document.body.innerText;
             return ['Request received.',
                     'We already have a recent request',
                     'We could not send your request.',
                     'reached the hourly request limit',
                     'You appear to be offline.'].some(s => t.includes(s));
           }""",
        timeout=25_000,
    )
    made = len(lead_posts()) - before
    EV.step("G5 two concurrent activations create exactly ONE lead request",
            made == 1, posts=made)

    # The OTHER double-submit shape: a second, deliberate send after the first
    # has completed. That is not a client race and must not be hidden — but it
    # must also not create a second lead. The server dedupes by address inside
    # 24h and the page must say so plainly instead of claiming a new request.
    page.goto(base + "/b2b", wait_until="networkidle")
    fill_valid(page, email)  # same address on purpose
    resp = submit_and_capture(page)
    body = page.inner_text("body")
    EV.step("G5 re-sending the same address is reported as already received",
            resp.status in (200, 201) and resp.json().get("duplicate") is True
            and "We already have a recent request" in body,
            status=resp.status, duplicate=resp.json().get("duplicate"))
    EV.step("G5 a duplicate is NOT dressed up as a new request",
            "Request received." not in body)


def goal_throttle(page, base: str) -> None:
    """Needs a fresh limiter window — see the module docstring."""
    seen_429 = False
    last = None
    for i in range(8):
        page.goto(base + "/b2b", wait_until="networkidle")
        fill_valid(page, unique_email(f"thr{i}"))
        try:
            resp = submit_and_capture(page, timeout_ms=15_000)
        except Invalid:
            raise
        except Exception:
            # No response arrived at all (client-side throttle guard may have
            # stopped the request). That is a legitimate branch, not a failure.
            break
        last = resp
        if resp.status == 429:
            seen_429 = True
            break

    EV.step("G6 the ceiling was actually reached", seen_429,
            last_status=last.status if last else None)
    if not seen_429:
        return

    body = page.inner_text("body")
    EV.step("G6 the page names the limit in its own voice",
            "This network has reached the hourly request limit." in body)
    EV.step("G6 it does NOT show the generic send failure",
            "We could not send your request." not in body)
    EV.step("G6 it offers email instead of retry",
            "Email partnerships instead" in body)

    mailto = page.get_by_role("link", name=re.compile(r"email partnerships", re.I))
    href = mailto.first.get_attribute("href") if mailto.count() else None
    EV.step("G6 the email affordance is a real mailto",
            (href or "").startswith("mailto:"), href=href)

    EV.step("G6 the typed values were not discarded",
            field(page, "company").input_value() == "E2E Verification Brand",
            company=field(page, "company").input_value())


def goal_server_422_shows_field_errors(page, base: str) -> None:
    """The client validates the same rules the server does, so an honest UI
    cannot produce a 422. Stub the server response to prove the UI branch."""
    page.goto(base + "/b2b", wait_until="networkidle")
    fill_valid(page, unique_email("422"))

    def stub(route):
        route.fulfill(
            status=422,
            content_type="application/json",
            body=json.dumps({"detail": {"error": {
                "code": "VALIDATION_ERROR",
                "message": "A valid work email is required.",
                "fields": {"work_email": "Enter a valid work email address."},
            }}}),
        )

    page.route(f"**{LEAD_ENDPOINT}", stub)
    submit_button(page).click()
    page.wait_for_function(
        "() => document.body.innerText.includes('could not send')", timeout=15_000)
    page.unroute(f"**{LEAD_ENDPOINT}")

    body = page.inner_text("body")
    EV.step("G7 a server 422 is reported as a validation failure",
            "We could not send your request." in body)
    EV.step("G7 the 422 detail tells the user what to fix",
            "Check the highlighted fields and submit again." in body)
    EV.step("G7 a 422 is never presented as success",
            "Request received." not in body)


def goal_network_dropout(page, base: str, ctx) -> None:
    """Two different failures that must not be conflated.

    (a) The request is aborted while the browser is still ONLINE. The honest
        answer is a generic, retryable failure — claiming "you are offline"
        here would be a lie, and the code branches on navigator.onLine.
    (b) The browser really is offline (context.set_offline). Only now may the
        page name the offline state.
    """
    # (a) aborted request, connection up
    page.goto(base + "/b2b", wait_until="networkidle")
    email = unique_email("abort")
    fill_valid(page, email)

    page.route(f"**{LEAD_ENDPOINT}", lambda route: route.abort("failed"))
    submit_button(page).click()
    page.wait_for_function(
        "() => document.body.innerText.includes('could not send')", timeout=15_000)
    page.unroute(f"**{LEAD_ENDPOINT}")

    body = page.inner_text("body")
    EV.step("G8a an aborted request is reported as a send failure",
            "We could not send your request." in body)
    EV.step("G8a it does NOT falsely claim the device is offline",
            "You appear to be offline." not in body)
    EV.step("G8a no false success after an aborted request",
            "Request received." not in body)
    EV.step("G8a the typed values survive the failure",
            field(page, "email").input_value() == email,
            email=field(page, "email").input_value())

    # (b) genuinely offline
    page.goto(base + "/b2b", wait_until="networkidle")
    fill_valid(page, unique_email("offline"))
    ctx.set_offline(True)
    try:
        submit_button(page).click()
        page.wait_for_function(
            "() => document.body.innerText.includes('offline')", timeout=15_000)
        body = page.inner_text("body")
        EV.step("G8b a truly offline submit is named as offline",
                "You appear to be offline." in body)
        EV.step("G8b no false success while offline",
                "Request received." not in body)
    finally:
        ctx.set_offline(False)


def goal_arabic_rtl(page, base: str) -> None:
    # House pattern (e2e_home_goals.py): the language lives in localStorage
    # under `confit_lang`, not in a query string.
    page.goto(base + "/b2b", wait_until="domcontentloaded")
    page.evaluate("localStorage.setItem('confit_lang', 'ar')")
    page.goto(base + "/b2b", wait_until="networkidle")
    dir_attr = page.evaluate("document.documentElement.getAttribute('dir')")
    EV.step("G9 the document is RTL in Arabic", dir_attr == "rtl", dir=dir_attr)

    body = page.inner_text("body")
    EV.step("G9 Arabic copy actually renders",
            re.search(r"[\u0600-\u06FF]{4,}", body) is not None)

    # The same form contract must hold in Arabic — labels are translated, so
    # query by the Arabic accessible names rather than reusing the English map.
    ar = {"company": "اسم الشركة", "contact": "اسم مسؤول التواصل",
          "email": "البريد الإلكتروني للعمل"}
    missing = []
    for key, label in ar.items():
        loc = page.get_by_role("textbox", name=re.compile(re.escape(label)))
        if loc.count() == 0:
            missing.append(f"{key}:{label}")
    EV.step("G9 the Arabic form keeps real accessible labels", not missing,
            missing=missing)

    ar_submit = page.get_by_role("button", name=re.compile(r"اطلب مراجعة الشراكة"))
    EV.step("G9 the Arabic submit is present and correctly worded",
            ar_submit.count() > 0)

    # Leave the shared page in English: the remaining goals query by the
    # English accessible names, and a leaked locale would look like a defect.
    page.evaluate("localStorage.setItem('confit_lang', 'en')")
    page.goto(base + "/b2b", wait_until="networkidle")


def goal_responsive(browser, base: str) -> None:
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    mpage = ctx.new_page()
    mpage.goto(base + "/b2b", wait_until="networkidle")

    overflow = mpage.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth")
    EV.step("G10 no horizontal overflow at 390px", overflow <= 1, overflow_px=overflow)

    form = mpage.get_by_role("form").first
    EV.step("G10 the lead form is reachable on a phone",
            form.count() > 0 and form.is_visible())

    email = unique_email("mobile")
    field(mpage, "company").fill("E2E Mobile Brand")
    field(mpage, "contact").fill("Mobile Contact")
    field(mpage, "email").fill(email)

    before = len(lead_posts())
    resp = submit_and_capture(mpage)
    EV.step("G10 the form is operable on a phone", resp.status == 201,
            status=resp.status, posts=len(lead_posts()) - before)

    # 48px touch floor on the control that matters most.
    box = submit_button(mpage).bounding_box()
    EV.step("G10 the submit meets the 48px touch floor",
            box is not None and box["height"] >= 48,
            height=box["height"] if box else None)
    ctx.close()


def goal_keyboard(page, base: str) -> None:
    page.goto(base + "/b2b", wait_until="networkidle")

    cta = page.get_by_role("button",
                           name=re.compile(r"request partnership", re.I)).first
    cta.focus()
    cta.press("Enter")
    focused = page.evaluate(
        "() => { const a = document.activeElement;"
        "  return a ? (a.tagName + '|' + (a.name || a.id || '')) : 'none'; }")
    EV.step("G11 the masthead CTA moves focus into the form",
            "INPUT" in focused or "TEXTAREA" in focused or "SELECT" in focused,
            focused=focused)

    fill_valid(page, unique_email("kbd"))
    submit = submit_button(page)
    submit.focus()

    # Stubbed on purpose: this goal is about keyboard operability, and server
    # persistence is already proven in G4. Spending another of the five
    # requests this endpoint allows per hour to re-prove it would crowd out
    # the throttle goal.
    page.route(f"**{LEAD_ENDPOINT}", lambda route: route.fulfill(
        status=201, content_type="application/json",
        body=json.dumps({"id": 900001, "status": "received",
                         "notification_status": "not_configured",
                         "duplicate": False, "message": "ok"})))
    submit.press("Enter")
    page.wait_for_function(
        "() => document.body.innerText.includes('CONFIT-900001')", timeout=15_000)
    page.unroute(f"**{LEAD_ENDPOINT}")
    EV.step("G11 the submit is operable by keyboard alone",
            "CONFIT-900001" in page.inner_text("body"))


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:43123")
    ap.add_argument("--out", default="/tmp/e2e_partner_gateway_goals.json")
    ap.add_argument("--phase", choices=["main", "throttle", "all"], default="all")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        wire_network(page)
        try:
            if args.phase in ("main", "all"):
                goal_arrival(page, base)
                goal_not_customer_signup(page)
                goal_client_validation_is_free(page, base)
                goal_happy_path(page, base, ctx)
                goal_double_click_single_lead(page, base)
                goal_server_422_shows_field_errors(page, base)
                goal_network_dropout(page, base, ctx)
                goal_arabic_rtl(page, base)
                goal_responsive(browser, base)
                goal_keyboard(page, base)
            if args.phase in ("throttle", "all"):
                goal_throttle(page, base)
        except Invalid as exc:
            EV.steps.append({"step": "RUN-INVALID", "ok": False, "err": str(exc)})
        finally:
            Path(args.out).write_text(json.dumps(
                {"steps": EV.steps,
                 "network_tail": EV.network[-40:],
                 "console_errors": EV.console_errors,
                 "created_emails": EV.created_emails,
                 "lead_posts": len(lead_posts())},
                indent=2, default=str))
            browser.close()

    failed = [s for s in EV.steps if not s["ok"]]
    print(f"\n{len(EV.steps) - len(failed)}/{len(EV.steps)} steps passed; "
          f"evidence: {args.out}")
    if EV.created_emails:
        print("test leads created (safe to delete): "
              + ", ".join(EV.created_emails))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
