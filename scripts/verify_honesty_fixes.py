"""Playwright verification for the audit-notes honesty fixes (local real stack).

Covers:
  H1  Home editorial cards: no fabricated "% Fit" numbers; honest "Curated Ensemble" chips.
  H2  Wardrobe 'My Looks' as GUEST: honest sign-in prompt; static mock GONE.
  H3  Wardrobe 'My Looks' as AUTHED shopper: real backend outfit appears (title + Match
      badge + real total), delete works, empty state honest. (Self-cleaning.)
  H4  Visual Search modal: real FILE UPLOAD -> POST /tryon/visual-search carries
      image_base64 data-URL -> REAL backend returns matches -> modal renders them.
  H5  Try-On modal: no pre-render score badge when nothing applied; upload trigger visible.
"""
import json, re, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
UPLOAD_IMG = "/home/user/test_person.jpg"
results = []

def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ("  | " + str(detail) if detail and not cond else ""))

# LOCAL stack creds: backend/.env points at the scratch DB (confit_fixverify),
# NOT the production database (proven: rotated password passes on
# confit-a.vercel.app but fails bcrypt on this DB). The scratch DB still has
# the pre-rotation seed password; it is used ONLY against localhost:8000.
shopper = ("shopper@confit.io", "Password123!")

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1360, "height": 900})
    page = ctx.new_page()
    captured_vs = {}
    def capture_vs(route):
        try:
            captured_vs["body"] = route.request.post_data
        except Exception:
            pass
        route.continue_()
    page.route("**/tryon/visual-search", capture_vs)

    # ---------- H1: Home ----------
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_timeout(800)
    body = page.locator("body").inner_text().lower()
    check("H1a home: no '% fit' text anywhere", "% fit" not in body,
          [l for l in body.splitlines() if "% fit" in l][:2])
    curated = page.get_by_text("curated ensemble", exact=False).count()
    check("H1b home: 'Curated Ensemble' honest chips >= 2", curated >= 2, curated)

    # ---------- H2: Wardrobe guest ----------
    page.goto(BASE + "/wardrobe", wait_until="networkidle")
    page.wait_for_timeout(600)
    page.get_by_role("button", name=re.compile("my looks", re.I)).click()
    page.wait_for_timeout(700)
    body = page.locator("body").inner_text().lower()
    check("H2a guest: honest sign-in prompt", "sign in to see your saved looks" in body)
    check("H2b guest: static mock ensemble GONE", "elevated metropolitan boardroom" not in body)
    check("H2c guest: fabricated $529.00 GONE", "529" not in body)

    # ---------- H3: Wardrobe authed ----------
    # Self-heal: remove any 'PW Verify Look' leftovers from earlier runs.
    import urllib.request
    def _api(path, data=None, method=None, hdr=None):
        # method=None → urllib infers POST when a body is present, GET otherwise
        req = urllib.request.Request("http://localhost:8000/api/v1" + path,
                                     data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json", **(hdr or {})},
                                     method=method)
        return json.load(urllib.request.urlopen(req))
    _tok = _api("/auth/login", {"email": shopper[0], "password": shopper[1]})
    _h = {"Authorization": "Bearer " + _tok["access_token"]}
    for _l in _api("/outfits", hdr=_h):
        if _l["title"] == "PW Verify Look":
            _api(f"/outfits/{_l['id']}", method="DELETE", hdr=_h)
    # REAL UI login first (AuthModal) — the API-created look must be visible
    # to an actually-authenticated browser session.
    page.goto(BASE + "/", wait_until="networkidle")
    page.get_by_role("button", name="Sign In").first.click()
    page.fill('input[type="email"]', shopper[0])
    page.fill('input[type="password"]', shopper[1])
    page.locator('button[type="submit"]:has-text("Sign In")').click()
    page.wait_for_timeout(2500)

    # create a real outfit for shopper via API (same DB the UI reads)
    import urllib.request
    login_req = urllib.request.Request(
        "http://localhost:8000/api/v1/auth/login",
        data=json.dumps({"email": shopper[0], "password": shopper[1]}).encode(),
        headers={"Content-Type": "application/json"})
    tok = json.load(urllib.request.urlopen(login_req))
    auth = {"Authorization": "Bearer " + tok["access_token"]}
    prods = json.load(urllib.request.urlopen("http://localhost:8000/api/v1/catalog/products?page_size=3"))
    item_ids = [x["id"] for x in (prods if isinstance(prods, list) else prods.get("items", prods))][:3]
    creq = urllib.request.Request(
        "http://localhost:8000/api/v1/outfits",
        data=json.dumps({"title": "PW Verify Look", "description": "created by verify script",
                         "occasion": "Work & Business", "product_ids": item_ids}).encode(),
        headers={**auth, "Content-Type": "application/json"})
    outfit = json.load(urllib.request.urlopen(creq))
    print("created outfit id:", outfit.get("id"), "total:", outfit.get("total_price"))

    page.goto(BASE + "/wardrobe", wait_until="networkidle")
    page.get_by_role("button", name=re.compile("my looks", re.I)).click()
    page.wait_for_timeout(1200)
    body = page.locator("body").inner_text().lower()
    check("H3a real saved look title renders", "pw verify look" in body)
    check("H3b badge says 'match' not '% fit'", ("% match" in body) and ("% fit" not in body))
    check("H3c real total shown (no hardcoded 529)", "529" not in body and "$" in body)
    # delete via UI — target ONLY the look this script created (aria-label)
    page.get_by_role("button", name="Delete PW Verify Look").click()
    try:
        page.get_by_text("PW Verify Look").wait_for(state="detached", timeout=10000)
        gone = True
    except Exception:
        gone = False
    check("H3d delete works -> look removed", gone)

    # ---------- H4: Visual Search real upload ----------
    page.goto(BASE + "/", wait_until="networkidle")
    page.get_by_role("button", name=re.compile("discover", re.I)).first.click()
    page.get_by_role("button", name=re.compile("visual search", re.I)).first.click()
    page.wait_for_selector("text=/upload your photo/i", timeout=8000)
    check("H4a visible 'Upload your photo' trigger", True)
    with page.expect_response("**/tryon/visual-search", timeout=30000) as resp_info:
        page.set_input_files("#vs-photo-upload", UPLOAD_IMG)
    b = captured_vs.get("body") or ""
    check("H4b POST carried image_base64 data-URL", '"image_base64":"data:image/' in (b or "").replace(" ", ""), len(b))
    # REAL backend answer: results_count > 0 and match cards actually rendered
    vs_resp = resp_info.value.json()
    check("H4c backend returned real matches",
          vs_resp.get("results_count", 0) >= 1, vs_resp.get("results_count"))
    page.wait_for_timeout(800)
    # match cards are identifiable by the "% Match" similarity chip inside them
    card_imgs = page.get_by_text(re.compile(r"% match", re.I)).count()
    check("H4d match cards rendered in modal", card_imgs >= min(3, vs_resp.get("results_count", 1)),
          f"cards={card_imgs} count={vs_resp.get('results_count')}")

    # ---------- H5: Try-On modal honesty ----------
    page.goto(BASE + "/product/1", wait_until="networkidle")
    page.wait_for_timeout(600)
    tryon_btn = page.get_by_role("button", name="Launch Virtual Try-On")
    tryon_btn.click()
    page.wait_for_timeout(1500)
    # scope STRICTLY to the try-on modal overlay (PDP itself legitimately
    # shows real size-recommendation badges like "95% Fit · Recommended M").
    # NOTE: launching from a PDP auto-applies that product as a layer and
    # starts a real render (designed flow) — so the badge IS shown, but must
    # use the honest wording: "…% Style Match · catalog heuristic — not a
    # drape fit" (or "engine verification pending…" mid-render). NEVER "% Fit".
    modal = page.locator("div.fixed.inset-0.z-50")
    modal_txt = modal.inner_text().lower()
    check("H5a badge honest when layer auto-applied from PDP",
          ("% fit" not in modal_txt) and ("style match" in modal_txt)
          and ("catalog heuristic" in modal_txt or "engine verification pending" in modal_txt),
          [l for l in modal_txt.splitlines() if "%" in l or "match" in l][:3])
    check("H5b try-on photo upload trigger visible", "upload photo" in modal_txt)
    page.locator("div.fixed.inset-0.z-50 button", has_text="✕").first.click(timeout=5000)
    page.wait_for_timeout(600)

    # H5c: remove the applied layer inside the modal → the score badge must
    # disappear entirely (no score presented on a bare base silhouette)
    page.goto(BASE + "/", wait_until="networkidle")
    page.get_by_role("button", name="Virtual Try-On", exact=True).first.click()
    page.wait_for_selector("text=/dressed with 1 garment layer/i", timeout=10000)
    # the dressed-layers panel lists the layer with a remove control
    removed = False
    for sel in ["button[title='Remove item']", "button:has-text('Remove')", "button:has-text('✕')"]:
        loc = page.locator("div.fixed.inset-0.z-50 " + sel)
        if loc.count() > 0:
            loc.first.click()
            removed = True
            break
    page.wait_for_timeout(1500)
    modal2_txt = page.locator("div.fixed.inset-0.z-50").inner_text().lower()
    check("H5c removing layer kills the score badge",
          removed and ("% style match" not in modal2_txt) and ("% fit" not in modal2_txt),
          f"removed={removed} " + str([l for l in modal2_txt.splitlines() if "%" in l][:3]))

    browser.close()

failed = [n for n, ok, _ in results if not ok]
print(f"\n== {len(results) - len(failed)}/{len(results)} PASS ==")
sys.exit(1 if failed else 0)
