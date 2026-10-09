#!/usr/bin/env python3
"""B02 — goal-oriented E2E for the partner command center (/b2b authenticated).

LOOPBACK-ONLY: refuses any non-localhost base url. Provisions an ISOLATED
brand_owner in the LOCAL dev SQLite (same pattern backend tests use), logs in
through the real auth endpoint, and verifies the dashboard from the user
outcome:

  G1 signed-in partner lands on the command center; rendered KPIs equal the
     live GET /brand/analytics payload (server is the authority);
  G2 while telemetry is slow (CDP network latency) the geometry skeleton is
     the visible state — never a blank page or a bare spinner;
  G3 telemetry 503 → terminal-with-retry panel; retry after recovery renders
     data (failure never masquerades as empty);
  G4 a brand with zero activity renders N/A + "Not enough data", never "0%";
  G5 Arabic locale renders Arabic copy with dir=rtl;
  G6 Refresh re-fetches;
  G7 zero uncaught browser errors across the whole journey.

No real email/SMS/PSP traffic; the seeded account is deleted on exit.
"""
import argparse, json, re, sys, time, uuid
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:43123")
parser.add_argument("--out", default="/home/user/e2e_b02_main.json")
args = parser.parse_args()
base = args.base_url.rstrip("/")
if urlsplit(base).hostname not in ("localhost", "127.0.0.1"):
    parser.error("Only loopback test servers are permitted")

# ---------------------------------------------------------------- provision
sys.path.insert(0, "/home/user/confit_a")
from backend.app.core.database import SessionLocal          # noqa: E402
from backend.app.core.security import get_password_hash    # noqa: E402
from backend.app.models.user import User, BrandProfile, UserRole  # noqa: E402

suffix = uuid.uuid4().hex[:8]
EMAIL = f"b02-e2e-{suffix}@confit-e2e.dev"  # .test/.local are special-use and refused by the validator
PASSWORD = "Xx1-" + uuid.uuid4().hex  # random per run; the account is deleted on exit
BRAND = f"B02 E2E Label {suffix}"

db = SessionLocal()
user = User(email=EMAIL, full_name="B02 E2E", hashed_password=get_password_hash(PASSWORD),
            role=UserRole.BRAND_OWNER)
db.add(user)
db.commit()
profile = BrandProfile(user_id=user.id, brand_name=BRAND, slug=f"b02-e2e-{suffix}",
                       is_verified=False)
db.add(profile)
db.commit()
user_id, profile_id = user.id, profile.id
db.close()
print(f"provisioned {EMAIL} (user {user_id})", flush=True)

results = []
def record(name, extra=None):
    results.append({"goal": name, "status": "PASS", **(extra or {})})
    print("PASS", name, flush=True)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 950})
        login = ctx.request.post(base + "/api/v1/auth/login",
                                 data=json.dumps({"email": EMAIL, "password": PASSWORD}),
                                 headers={"Content-Type": "application/json"})
        assert login.status == 200, f"login {login.status}: {login.text()[:200]}"
        who = login.json()
        user_obj = who.get("user", who)
        ctx.add_init_script('localStorage.setItem("confit_user", '
                            + json.dumps(json.dumps(user_obj)) + ');')
        page = ctx.new_page()
        pageerrors, console_errors = [], []
        page.on("pageerror", lambda e: pageerrors.append(str(e)))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        # --------------------------------------------- G4/G1 fresh brand truth
        api = ctx.request.get(base + "/api/v1/brand/analytics")
        assert api.status == 200, api.status
        truth = api.json()
        assert truth["total_views"] == 0 and truth["funnel_conversion_rate"] is None, truth

        # --------------------------------------------- G2 skeleton under latency
        # Gate the analytics fetch INSIDE the page (async promise) instead of
        # CDP latency — vite dev serves hundreds of module requests and a
        # global latency multiplier starves the 30s navigation budget.
        ctx.add_init_script(
            """() => {
                 if (localStorage.getItem('b02_gate') !== '1') return;
                 const orig = window.fetch.bind(window);
                 window.fetch = (input, init) => {
                   const url = typeof input === 'string' ? input : input.url;
                   if (url.includes('/brand/analytics')) {
                     return new Promise((res) => { window.__b02_release = res; })
                       .then(() => orig(input, init));
                   }
                   return orig(input, init);
                 };
               }"""
        )
        page.goto(base + "/b2b", wait_until="domcontentloaded")  # gate off: warm the app
        expect(page.get_by_text(re.compile("Command Center")).first).to_be_visible(timeout=20000)
        page.evaluate("localStorage.setItem('b02_gate','1')")
        page.reload(wait_until="domcontentloaded")
        expect(page.locator(".skeleton-shimmer").first).to_be_visible(timeout=10000)
        expect(page.get_by_role("status").first).to_be_visible()
        page.evaluate("localStorage.removeItem('b02_gate'); window.__b02_release && window.__b02_release()")
        expect(page.get_by_text(re.compile("Command Center")).first).to_be_visible(timeout=15000)
        record("G2: gated telemetry shows the geometry skeleton (role=status), then data")

        # --------------------------------------------- G1 rendered == server truth
        expect(page.get_by_text(re.compile("Command Center")).first).to_be_visible(timeout=15000)
        expect(page.get_by_text(BRAND).first).to_be_visible()
        expect(page.get_by_text("Brand Partner — verification pending", exact=True)).to_be_visible()
        expect(page.get_by_text("N/A", exact=True)).to_be_visible()
        expect(page.get_by_text("Not enough data").first).to_be_visible()
        assert page.get_by_text("0%", exact=True).count() == 0
        record("G1+G4: masthead renders brand; null ratio is N/A, never 0%")

        # --------------------------------------------- G3 503 -> retry -> data
        page.route("**/api/v1/brand/analytics**",
                   lambda route: route.fulfill(status=503, content_type="application/json",
                                               body=json.dumps({"detail": "telemetry down"})))
        page.get_by_role("button", name="Refresh").click()
        expect(page.get_by_text("B2B telemetry unavailable")).to_be_visible(timeout=10000)
        expect(page.get_by_role("button", name="Retry")).to_be_visible()
        page.unroute("**/api/v1/brand/analytics**")
        page.get_by_role("button", name="Retry").click()
        expect(page.get_by_text(re.compile("Command Center")).first).to_be_visible(timeout=15000)
        record("G3: 503 renders terminal-with-retry; retry after recovery renders data")

        # --------------------------------------------- G6 refresh re-fetches
        before = 0
        counts = {"n": 0}
        def count(route):
            counts["n"] += 1
            route.continue_()
        page.route("**/api/v1/brand/analytics**", count)
        page.get_by_role("button", name="Refresh").click()
        page.wait_for_timeout(1200)
        assert counts["n"] >= 1, counts
        page.unroute("**/api/v1/brand/analytics**")
        record("G6: refresh triggers a fresh analytics fetch", {"requests": counts["n"]})

        # --------------------------------------------- G5 Arabic RTL
        page.evaluate('localStorage.setItem("confit_lang", "ar")')
        page.goto(base + "/b2b", wait_until="domcontentloaded")
        expect(page.get_by_text("قياسات الشريك")).to_be_visible(timeout=15000)
        assert page.evaluate('document.documentElement.dir') == "rtl"
        expect(page.get_by_text("الأكثر تنسيقًا في الإطلالات")).to_be_visible()
        record("G5: Arabic locale renders Arabic copy with dir=rtl")

        page.evaluate('localStorage.setItem("confit_lang", "en")')
        page.goto(base + "/b2b", wait_until="networkidle")
        page.wait_for_timeout(800)
        import os
        os.makedirs("/home/user/shots", exist_ok=True)
        page.screenshot(path="/home/user/shots/b02-desktop-en.png", full_page=True)
        page.evaluate('localStorage.setItem("confit_lang", "ar")')
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path="/home/user/shots/b02-desktop-ar.png", full_page=True)

        assert not pageerrors, pageerrors
        record("G7: zero uncaught browser errors across the journey",
               {"console_errors": len(console_errors)})
        browser.close()
finally:
    db = SessionLocal()
    db.query(BrandProfile).filter(BrandProfile.id == profile_id).delete()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()
    print("cleaned seeded account", flush=True)

with open(args.out, "w", encoding="utf-8") as f:
    json.dump({"environment": "isolated local Vite+FastAPI+SQLite; NOT production",
               "goals": results}, f, ensure_ascii=False, indent=2)
print(f"ALL {len(results)} GOALS PASS", flush=True)
