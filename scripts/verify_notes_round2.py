"""Production re-verification for audit notes round 2 (2026-09-06, post PR#68).

Probes against https://confit-a.vercel.app:
  R1  /b2b gate: 'Sign In to Continue' / 'Create New Account' actually open the AuthModal.
  R2  Visual Search SAMPLE path (Navy Wool Blazer): completes or shows honest error — never stuck 'Analyzing...'.
  R3  Visual Search modal has visible upload trigger.
  R4  /fit renders the No-Photo Measurement form (not the try-on studio grid).
  R5  Wardrobe guest closet copy honest (no fake 'Scanning...' forever)?
  R6  Try-On modal: no '% Fit' fabrications; honest style-match wording.
  R7  Home 'View All Catalog' count: honest during load (no misleading '(0)').
  R8  Home claims: 'On-Device Biometric Vision' + '71%' present? (claims audit)
  R9  AuthModal shows explicit error on bad credentials.
"""
import re, sys, json, urllib.request
from playwright.sync_api import sync_playwright

BASE = "https://confit-a.vercel.app"
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  | {detail}" if detail and not cond else ""))

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_context(viewport={"width": 1360, "height": 900}).new_page()

    # R7/R8: Home
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(1500)
    home = pg.locator("body").inner_text()
    m = re.search(r"View All Catalog\s*\((\d+)\)", home)
    check("R7 catalog count visible & non-zero after load", m is not None and m.group(1) != "0", m.group(0) if m else "not found")
    # PR #69 closed both claims — they must be ABSENT now, with the honest
    # replacement card present (regression gate, inverted from the old
    # pre-fix detection probes).
    check("R8a 'On-Device Biometric Vision' claim ABSENT (PR#69)",
          "On-Device Biometric Vision" not in home and "Private In-Browser Fit Studio" in home)
    check("R8b '71%' claim ABSENT (PR#69, EN+AR copies removed)",
          "71%" not in home)

    # R1: /b2b dead buttons?
    pg.goto(BASE + "/b2b", wait_until="networkidle"); pg.wait_for_timeout(1500)
    gate = pg.locator("body").inner_text()
    if "Access Governance" in gate or "Sign In to Continue" in gate.lower() or re.search(r"sign in to continue", gate, re.I):
        btn = pg.get_by_role("button", name=re.compile("sign in to continue", re.I)).first
        btn.click()
        pg.wait_for_timeout(1500)
        after = pg.locator("body").inner_text()
        modal_open = ("Verify & Sign In" in after) or ('input[type="email"]' and pg.locator('div.fixed.inset-0.z-50 input[type="email"]').count() > 0) or pg.locator('input[type="email"]').count() > 0
        check("R1a b2b 'Sign In to Continue' opens auth modal", modal_open)
        if modal_open:
            pg.locator("div.fixed.inset-0.z-50 button", has_text="✕").first.click()
            pg.wait_for_timeout(700)
        reg = pg.get_by_role("button", name=re.compile("create new account", re.I)).first
        reg.click(); pg.wait_for_timeout(1500)
        after2 = pg.locator("body").inner_text()
        check("R1b 'Create New Account' opens register modal",
              ("Full Name" in after2) or ("Create Account" in after2) or pg.locator('input[type="password"]').count() > 0)
        pg.locator("div.fixed.inset-0.z-50 button", has_text="✕").first.click()
        pg.wait_for_timeout(700)
    else:
        # already signed in as consumer (persisted) → guard not shown
        check("R1 b2b gate shown (else signed-in consumer detected)", "Brand" in gate or "Dashboard" in gate, gate[:120])

    # R2/R3/R6: visual search on /discover
    pg.goto(BASE + "/discover", wait_until="networkidle"); pg.wait_for_timeout(1500)
    pm = pg.get_by_role("button", name=re.compile("photo match", re.I)).first
    pm.click(); pg.wait_for_timeout(1200)
    body = pg.locator("body").inner_text()
    check("R3 VS modal upload trigger visible", re.search(r"upload your photo", body, re.I) is not None)
    sample = pg.get_by_role("button", name=re.compile("navy wool blazer", re.I)).first
    if sample.count() == 0:
        sample = pg.get_by_text("Navy Wool Blazer", exact=False).first
    sample.click()
    try:
        with pg.expect_response("**/tryon/visual-search", timeout=40000) as ri:
            pass
        resp = ri.value
        ok_api = resp.status == 200
        cnt = resp.json().get("results_count")
        check("R2a sample search API answered 200", ok_api, resp.status)
        pg.wait_for_timeout(1500)
        body2 = pg.locator("body").inner_text()
        rendered = re.search(r"% match", body2, re.I) is not None
        errored = re.search(r"unavailable|failed|try again", body2, re.I) is not None
        check("R2b results rendered or honest error (never stuck Analyzing)",
              (rendered or errored) and ("Analyzing..." not in body2), f"count={cnt} rendered={rendered} errored={errored}")
    except Exception as e:
        check("R2a sample search API answered 200", False, f"no response in 40s: {str(e)[:80]}")

    # R6: try-on modal honesty
    pg.goto(BASE + "/product/1", wait_until="networkidle"); pg.wait_for_timeout(1200)
    pg.get_by_role("button", name="Launch Virtual Try-On").click(); pg.wait_for_timeout(2000)
    modal = pg.locator("div.fixed.inset-0.z-50").first
    mt = modal.inner_text()
    check("R6 no '% Fit' fabrication; honest style-match wording",
          ("% fit" not in mt.lower()) and ("Style Match" in mt), [l for l in mt.splitlines() if "%" in l][:2])

    # R4: /fit content
    pg.goto(BASE + "/fit", wait_until="networkidle"); pg.wait_for_timeout(1500)
    fit = pg.locator("body").inner_text()
    has_form = pg.locator('input[type="number"], select').count() > 0 and re.search(r"(height|cm|measure)", fit, re.I) is not None
    check("R4 /fit shows measurement form (not just product grid)", has_form,
          f"numbers={pg.locator('input[type=number]').count()} selects={pg.locator('select').count()}")

    # R5: wardrobe guest closet
    pg.goto(BASE + "/wardrobe", wait_until="networkidle"); pg.wait_for_timeout(1500)
    ward = pg.locator("body").inner_text()
    check("R5 wardrobe guest: no endless 'Scanning your wardrobe' fake state",
          "Scanning your wardrobe" not in ward, [l for l in ward.splitlines() if "Scanning" in l][:1])

    # R9: auth modal bad-credentials feedback
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(1000)
    pg.get_by_role("button", name="Sign In").first.click(); pg.wait_for_timeout(800)
    pg.fill('input[type="email"]', "shopper@confit.io")
    pg.fill('input[type="password"]', "confit@1234")
    with pg.expect_response("**/auth/login", timeout=20000) as li:
        pg.locator('button[type="submit"]:has-text("Sign In")').click()
    code = li.value.status
    pg.wait_for_timeout(1200)
    # PR #69: an auth-attempt 401 must surface the SERVER's message
    # ('Invalid email or password.') in the modal's .text-rose-700 block —
    # NOT the generic sign-in nudge.
    err_visible = False
    try:
        blocks = pg.locator("div.fixed.inset-0.z-50 .text-rose-700")
        for a in blocks.all():
            if a.is_visible() and "Invalid email or password" in a.inner_text():
                err_visible = True; break
    except Exception:
        pass
    body_txt = pg.locator("body").inner_text()
    nudge_is_error = "Sign in to access your personal style profile" in body_txt and err_visible is False
    check("R9 401 answered and explicit server error shown (not the generic nudge)",
          code == 401 and err_visible and not nudge_is_error, f"code={code} err_visible={err_visible}")

    # R10: no raw i18n keys anywhere (audit: nav.wardrobe / nav.vton_studio /
    # nav.fit_finder leaked into the UI)
    pg.goto(BASE + "/", wait_until="networkidle"); pg.wait_for_timeout(1200)
    home_txt = pg.locator("body").inner_text()
    import re as _re
    raw_keys = _re.findall(r"\b(?:nav|footer|wardrobe|stylist)\.[a-z_]{4,}\b", home_txt)
    check("R10 no raw translation keys in rendered UI", not raw_keys, raw_keys[:4])

    # R11: 'verified styles' reworded to the honest catalog wording (PR#69)
    pg.goto(BASE + "/tryon-studio", wait_until="networkidle"); pg.wait_for_timeout(1200)
    ts_txt = pg.locator("body").inner_text()
    check("R11 'verified styles' claim gone; honest catalog wording",
          "verified styles" not in ts_txt and "styles from the live catalog" in ts_txt)

    # R12: /builder — Enter (keyboard) path REALLY adds to state as a guest:
    # Running Total must leave $0.00 (audit's core builder complaint)
    pg.goto(BASE + "/builder", wait_until="networkidle"); pg.wait_for_timeout(1200)
    # product cards are real <button aria-label="Add {title} to outfit"> —
    # the keyboard (Enter) path the audit demanded
    card = pg.locator('button[aria-label^="Add "][aria-label$="to outfit"]').first
    card.focus(); card.press("Enter"); pg.wait_for_timeout(1500)
    bt = pg.locator("body").inner_text()
    m_tot = re.search(r"Running Total:?\s*\$([\d,]+\.\d\d)", bt, re.S)
    tot = float(m_tot.group(1).replace(",", "")) if m_tot else -1
    check("R12 builder Enter adds item -> Running Total > $0", tot > 0, f"total={tot}")

    b.close()

failed = [n for n, ok, _ in results if not ok]
print(f"\n== {len(results)-len(failed)}/{len(results)} PASS ==")
sys.exit(1 if failed else 0)
