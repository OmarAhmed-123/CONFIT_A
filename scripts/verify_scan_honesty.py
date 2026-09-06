"""Playwright verification: CameraScan 'Size Studio' honesty (fix/scan-honesty).

Drives the REAL modal flow (Try-On modal → Live Scan → Manual Ruler sliders →
Compile) against the real local stack and asserts:
  S1  No fake CV claims anywhere ("Keypoints Locked", "V-Taper Matrix",
      "Biometric Scan Verified", "On-Device Computer Vision").
  S2  Honest framing present ("Size Profile Ready — self-reported",
      "Compile My Size Profile").
  S3  The measurement-session POST carries the user's ACTUAL slider value
      (not the height-ratio re-derivation) and honest calibration_method.
  S4  Confidence equals the documented model value (40 + 15/extra input,
      cap 85 manual / 80 preset), NOT the old hardcoded 97/94/95.
  S5  Preset path caps at 80% and discloses the preset basis.
"""
import json, re, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  | {detail}" if detail and not cond else ""))

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_context(viewport={"width": 1360, "height": 900}).new_page()
    submits = []
    def capture_submit(route):
        try:
            submits.append(route.request.post_data)
        except Exception:
            pass
        route.continue_()
    page.route("**/measurements/sessions/*/results", capture_submit)

    page.goto(BASE + "/product/1", wait_until="networkidle")
    page.get_by_role("button", name="Launch Virtual Try-On").click()
    page.wait_for_timeout(1200)
    # try-on modal overlay is the first .fixed.inset-0.z-50; Live Scan opens
    # the scan modal which mounts ANOTHER overlay after it (same class) —
    # the scan modal is therefore always overlays.last()
    page.locator("div.fixed.inset-0.z-50").first.get_by_role("button", name=re.compile("live scan", re.I)).first.click()
    page.wait_for_timeout(1000)
    scan = page.locator("div.fixed.inset-0.z-50").last

    # go to Manual Ruler tab (CTA lives there) and set shoulder to a value
    # the ratio model would NEVER produce from height 178 (ratio -> 46). 51.
    scan.get_by_role("button", name=re.compile("manual ruler", re.I)).first.click()
    page.wait_for_timeout(600)
    modal_txt = scan.inner_text()
    check("S2a honest CTA 'Compile My Size Profile'", "Compile My Size Profile" in modal_txt)
    check("S1a no fake CV step strings pre-run",
          all(x not in modal_txt for x in ["Keypoints Locked", "V-Taper Matrix", "Biometric Scan Verified",
                                           "On-Device Computer Vision", "Confirm & Evaluate Sizing"]))
    shoulder = scan.locator('input[type="range"][min="38"][max="56"]')
    shoulder.focus()
    for _ in range(5):
        shoulder.press("ArrowRight")   # 46 -> 51
    page.wait_for_timeout(300)
    scan.get_by_role("button", name="Compile My Size Profile").click()
    page.wait_for_timeout(2500)

    body = scan.inner_text()
    body_l = body.lower()
    check("S2b honest result header", "size profile ready" in body_l and "self-reported" in body_l)
    check("S1b no fake CV strings post-run",
          all(x not in body for x in ["Keypoints Locked", "V-Taper Matrix", "Biometric Scan Verified"]))
    check("S4a confidence is model-derived (55 = 40+15 for height+shoulder), not hardcoded 94/95/97",
          "55% Confidence" in body,
          [l for l in body.splitlines() if "Confidence" in l][:3])

    # S3: inspect the persisted measurement session payload
    ok_payload = False; detail = ""
    for post in submits:
        try:
            data = json.loads(post)
        except Exception:
            continue
        if data.get("shoulder_width_cm") == 51:
            ok_payload = data.get("calibration_method", "").startswith("self_reported_inputs_") and data.get("confidence_score") == 55
            detail = json.dumps(data)[:160]
    check("S3 payload carries REAL slider value + honest method + model confidence", ok_payload, detail or f"no matching submit among {len(submits)}")

    # S5: preset path caps at 80%
    scan.get_by_role("button", name=re.compile("retake", re.I)).first.click()
    page.wait_for_timeout(800)
    scan.get_by_role("button", name=re.compile("presets", re.I)).first.click()
    page.wait_for_timeout(600)
    preset_cards = scan.get_by_text(re.compile(r"\d{3} cm")).first
    preset_cards.click()
    page.wait_for_timeout(2500)
    body2 = scan.inner_text()
    m = re.search(r"(\d+)% Confidence", body2)
    conf = int(m.group(1)) if m else -1
    check("S5 preset path confidence capped at 80", conf == 80, f"found={conf}")
    check("S5b preset disclosure present", "preset silhouette" in body2.lower())

    b.close()

failed = [n for n, ok, _ in results if not ok]
print(f"\n== {len(results)-len(failed)}/{len(results)} PASS ==")
sys.exit(1 if failed else 0)
