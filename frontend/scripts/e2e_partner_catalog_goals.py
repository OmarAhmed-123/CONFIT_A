#!/usr/bin/env python3
"""B03 — goal-oriented E2E for /b2b/catalog (loopback-only).

Provisions an isolated brand_owner in the LOCAL dev SQLite, logs in through the
real auth endpoint, then verifies from the user outcome:

  G1 fresh brand sees the honest empty state with the upload CTA;
  G2 real CSV upload through the hidden input -> product row renders, last-import
     panel reports accepted rows, jobs ledger shows a terminal status;
  G3 stock edit persists: "{n} units" re-renders from the refreshed payload;
  G4 auto-tag issues a real POST and renders an HONEST state (preview when a
     worker exists, explicit failure when not — never invented tags);
  G5 Arabic locale renders Arabic with dir=rtl;
  G6 zero uncaught browser errors.

The seeded account is deleted on exit. No production traffic, ever.
"""
import argparse, json, re, sys, uuid
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:43123")
parser.add_argument("--out", default="/home/user/e2e_b03_main.json")
args = parser.parse_args()
base = args.base_url.rstrip("/")
if urlsplit(base).hostname not in ("localhost", "127.0.0.1"):
    parser.error("Only loopback test servers are permitted")

sys.path.insert(0, "/home/user/confit_a")
from backend.app.core.database import SessionLocal          # noqa: E402
from backend.app.core.security import get_password_hash    # noqa: E402
from backend.app.models.user import User, BrandProfile, UserRole  # noqa: E402

suffix = uuid.uuid4().hex[:8]
EMAIL = f"b03-e2e-{suffix}@confit-e2e.dev"
PASSWORD = "Xx1-" + uuid.uuid4().hex
BRAND = f"B03 E2E Label {suffix}"

from backend.app.models.catalog import Category  # noqa: E402

db = SessionLocal()
user = User(email=EMAIL, full_name="B03 E2E", hashed_password=get_password_hash(PASSWORD),
            role=UserRole.BRAND_OWNER)
db.add(user)
db.commit()
profile = BrandProfile(user_id=user.id, brand_name=BRAND, slug=f"b03-e2e-{suffix}",
                       is_verified=False)
db.add(profile)
db.commit()
user_id, profile_id = user.id, profile.id
# the importer refuses unknown category slugs; ensure the fixture category exists
made_category = False
if not db.query(Category).filter_by(slug="coats").first():
    db.add(Category(name="Coats", name_ar="معاطف", slug="coats"))
    db.commit()
    made_category = True
db.close()
print(f"provisioned {EMAIL} (user {user_id})", flush=True)

results = []
def record(name, extra=None):
    results.append({"goal": name, "status": "PASS", **(extra or {})})
    print("PASS", name, flush=True)

CSV = ("title,category_slug,base_price,color_family,thumbnail_url,sku_code,size,color,stock_level\n"
       "معطف اختبار,coats,19.99,Navy,https://example.com/coat.jpg,E2E-COAT,M,Navy,10\n")

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 950})
        login = ctx.request.post(base + "/api/v1/auth/login",
                                 data=json.dumps({"email": EMAIL, "password": PASSWORD}),
                                 headers={"Content-Type": "application/json"})
        assert login.status == 200, f"login {login.status}: {login.text()[:200]}"
        who = login.json()
        ctx.add_init_script('localStorage.setItem("confit_user", '
                            + json.dumps(json.dumps(who.get("user", who))) + ');')
        page = ctx.new_page()
        pageerrors = []
        page.on("pageerror", lambda e: pageerrors.append(str(e)))

        # ------------------------------------------------ G1 honest empty state
        page.goto(base + "/b2b/catalog", wait_until="domcontentloaded")
        expect(page.get_by_text("No products yet")).to_be_visible(timeout=20000)
        expect(page.get_by_role("button", name="Upload CSV")).to_be_visible()
        record("G1: fresh brand sees honest empty state with upload CTA")

        # ------------------------------------------------ G2 real CSV upload
        page.get_by_role("button", name="Bulk CSV Import").click()
        page.locator('input[type="file"]').set_input_files(
            {"name": "smoke.csv", "mimeType": "text/csv", "buffer": CSV.encode()})
        expect(page.get_by_text("معطف اختبار").first).to_be_visible(timeout=20000)
        expect(page.get_by_text(re.compile(r"Last import:")).first).to_be_visible()
        expect(page.get_by_text("Completed").first).to_be_visible(timeout=20000)
        page.get_by_role("dialog").get_by_role("button", name="Cancel").click()
        record("G2: CSV upload -> product row + last-import panel + terminal job")

        # ------------------------------------------------ G3 stock edit persists
        page.get_by_text("Edit Stock", exact=True).click()
        page.get_by_label("Stock for E2E-COAT").fill("12")
        page.get_by_role("button", name="Save", exact=True).click()
        expect(page.get_by_text("12 units", exact=True)).to_be_visible(timeout=20000)
        record("G3: stock edit persists and re-renders from refreshed payload")

        # ------------------------------------------------ G4 honest auto-tag
        page.get_by_role("button", name="Auto-tag with AI").click()
        honest = page.get_by_text(re.compile(r"Tagging failed:|confidence|limit reached"))
        expect(honest.first).to_be_visible(timeout=30000)
        record("G4: auto-tag renders an honest state (preview or explicit failure)")

        # ------------------------------------------------ G5 Arabic RTL
        page.evaluate('localStorage.setItem("confit_lang", "ar")')
        page.goto(base + "/b2b/catalog", wait_until="domcontentloaded")
        expect(page.get_by_text("إدارة الكتالوج ووحدات SKU")).to_be_visible(timeout=20000)
        assert page.evaluate('document.documentElement.dir') == "rtl"
        expect(page.get_by_text("تعديل المخزون")).to_be_visible()
        record("G5: Arabic locale renders Arabic with dir=rtl")

        assert not pageerrors, pageerrors
        record("G6: zero uncaught browser errors")
        browser.close()
finally:
    from backend.app.models.catalog import Product as ProductModel, ProductSKU
    db = SessionLocal()
    # delete jobs too: orphaned import jobs + SQLite rowid reuse would otherwise
    # surface this run's jobs to a later brand that receives the same id
    from backend.app.models.catalog_import import CatalogImportJob
    db.query(CatalogImportJob).filter(CatalogImportJob.brand_id == profile_id).delete(synchronize_session=False)
    prod_ids = [r[0] for r in db.query(ProductModel.id).filter(ProductModel.brand_id == profile_id).all()]
    if prod_ids:
        db.query(ProductSKU).filter(ProductSKU.product_id.in_(prod_ids)).delete(synchronize_session=False)
        db.query(ProductModel).filter(ProductModel.id.in_(prod_ids)).delete(synchronize_session=False)
    db.query(BrandProfile).filter(BrandProfile.id == profile_id).delete()
    db.query(User).filter(User.id == user_id).delete()
    if made_category:
        db.query(Category).filter_by(slug="coats").delete()
    db.commit()
    db.close()
    print("cleaned seeded account", flush=True)

with open(args.out, "w", encoding="utf-8") as f:
    json.dump({"environment": "isolated local Vite+FastAPI+SQLite; NOT production",
               "goals": results}, f, ensure_ascii=False, indent=2)
print(f"ALL {len(results)} GOALS PASS", flush=True)
