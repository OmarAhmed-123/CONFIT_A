import sys, json, base64, io, sqlite3, httpx
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2e_live_api_lib import *
from PIL import Image

results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail)) if detail else "", flush=True)

shopper = login("shopper@confit.io")
admin = login("admin@confit.io")
anon = httpx.Client(base_url=BASE, timeout=60)

# ---- product catalogue (ground truth from the DB) ----
con = db()
prod_rows = con.execute("select id, title from products").fetchall()
catalogue_ids = {r[0] for r in prod_rows}
catalogue_names = {r[1] for r in prod_rows}
print("catalogue products:", len(catalogue_ids))

def rec_product_ids(d):
    ids = []
    for rec in d.get("recommendations") or []:
        for it in rec.get("items", []) or []:
            pid = it.get("product_id") or it.get("id")
            if pid is not None: ids.append(pid)
    return ids

# ---- 1. Mode B text, signed in ----
r = shopper.post("/stylist/chat", json={"prompt": "a smart casual dinner look", "include_wardrobe_items": False}, headers=csrf(shopper))
d = r.json()
check("B1 text chat 200 for signed-in shopper", r.status_code == 200, r.status_code)
check("B2 text chat reports mode B and no fallback reason", d.get("mode") == "B" and not d.get("fallback_reason"), (d.get("mode"), d.get("fallback_reason")))
check("B3 engine honestly named (no fake provider name)", "Grounded" in (d.get("engine") or ""), d.get("engine"))
recs = d.get("recommendations") or []
check("B4 at least one recommendation returned", len(recs) >= 1, len(recs))
pids = rec_product_ids(d)
check("B5 every recommended product id exists in the catalogue", pids and all(p in catalogue_ids for p in pids), f"{len(pids)} ids, all in catalogue={all(p in catalogue_ids for p in pids)}")

# ---- 2. Authentication ----
# Guest text styling is intended (controller accepts anonymous callers and
# rate-limits them; only saving requires sign-in). Verify the guest path answers
# honestly and is attributed to no account.
r = anon.post("/stylist/chat", json={"prompt": "smart casual"})
check("A1 guest text chat answered (by design) with grounded Mode B", r.status_code == 200 and r.json().get("mode") == "B", r.status_code)

# ---- 3. Mode A: image submitted, no vision provider configured ----
r = shopper.post("/stylist/chat", json={"prompt": "put together a look around this blazer", "images": [png_data_url((30, 40, 110))]}, headers=csrf(shopper))
d = r.json()
check("MA1 photo request accepted (200) through the real service", r.status_code == 200, r.status_code)
check("MA2 honest fallback: mode B with a reason, not a fabricated analysis",
      d.get("mode") == "B" and bool(d.get("fallback_reason")) and (d.get("image_analysis") or {}).get("available") is False,
      {"mode": d.get("mode"), "reason": d.get("fallback_reason"), "ia": d.get("image_analysis")})
check("MA3 no image colours reported as analysed", not (d.get("image_analysis") or {}).get("colours"), "")
pids = rec_product_ids(d)
check("MA4 photo-turn recommendations still grounded in catalogue", all(p in catalogue_ids for p in pids), len(pids))

# ---- 4. Mode A upload limits ----
def expect(name, images, want):
    r = shopper.post("/stylist/chat", json={"prompt": "look around this", "images": images}, headers=csrf(shopper))
    check(name, r.status_code in want, f"HTTP {r.status_code}")
big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10)).decode()
expect("L1 four images refused (limit 3)", [png_data_url()] * 4, (422,))
expect("L2 image over 1 MB refused", ["data:image/png;base64," + big], (422,))
gif = base64.b64encode(b"GIF89a" + b"\x00" * 40).decode()
expect("L3 GIF data refused (only PNG/JPEG/WebP)", ["data:image/gif;base64," + gif], (422,))
expect("L4 mislabelled bytes refused (magic check)", ["data:image/png;base64," + base64.b64encode(b"not an image at all").decode()], (422,))
expect("L5 non-data URL refused", ["https://example.com/a.png"], (422,))

# Guests may send photos, but the per-caller image budget must engage (429),
# and the server must never answer 5xx for them.
codes = []
budget_429 = False
for _ in range(6):
    rr = anon.post("/stylist/chat", json={"prompt": "look", "images": [png_data_url()]})
    codes.append(rr.status_code)
    if rr.status_code == 429 and "styling with photos" in rr.text:
        budget_429 = True
        break
check("L6 guest photo budget enforced (image-budget 429, no 5xx)", budget_429 and not any(c >= 500 for c in codes), codes)

# ---- 5. Stored data: no base64 image in stylist tables ----
con = db()
tabs = [t for (t,) in con.execute("select name from sqlite_master where type='table' and name like '%stylist%' or name like '%outfit%' or name like '%wardrobe%'")]
hits = 0
for t in tabs:
    cols = [c[1] for c in con.execute(f"pragma table_info({t})") if c[2].upper().startswith(("TEXT","VARCHAR","JSON","CLOB")) or c[2]=="" ]
    for c in cols:
        n = con.execute(f"select count(*) from {t} where cast({c} as text) like '%data:image%' or cast({c} as text) like '%;base64,%'").fetchone()[0]
        hits += n
check("ST1 no data:image / base64 image text in stylist/outfit/wardrobe tables", hits == 0, f"tables={len(tabs)} hits={hits}")

# ---- 6. Wardrobe inclusion on/off, and isolation ----
wr = shopper.post("/wardrobe/items", json={"title": "E2E Navy Tailored Blazer", "category": "Outerwear", "color_name": "Navy", "color_hex": "#1B2A4A", "image_url": "https://example.com/e2e-blazer.jpg", "occasions": ["smart casual"]}, headers=csrf(shopper))
check("W0 wardrobe item created for shopper", wr.status_code in (200, 201), wr.status_code)
wid = wr.json().get("id") if wr.status_code in (200, 201) else None

def chat_wardrobe(client, flag):
    r = client.post("/stylist/chat", json={"prompt": "a smart casual look for dinner", "include_wardrobe_items": flag}, headers=csrf(client))
    return r.status_code, (r.json() if r.status_code == 200 else {})
def wardrobe_meta(d):
    intent = d.get("intent_detected") or {}
    return intent.get("wardrobe") or {}

off_code, off = chat_wardrobe(shopper, False)
on_code, on = chat_wardrobe(shopper, True)
def mentions_wardrobe(d):
    blob = json.dumps(d, ensure_ascii=False)
    return "E2E Navy Tailored Blazer" in blob
check("W1 wardrobe OFF: chat 200, wardrobe not requested/used, item absent", off_code == 200 and wardrobe_meta(off).get("used") is False and not mentions_wardrobe(off), (off_code, wardrobe_meta(off)))
check("W2 wardrobe ON: engine consulted the shopper's wardrobe (used=true, >=1 piece)", on_code == 200 and wardrobe_meta(on).get("used") is True and (wardrobe_meta(on).get("owned_items_considered") or 0) >= 1, (on_code, wardrobe_meta(on)))
adm_code, adm_on = chat_wardrobe(admin, True)
check("W3 other user (admin): chat 200 and shopper's wardrobe item never appears", adm_code == 200 and not mentions_wardrobe(adm_on), (adm_code, wardrobe_meta(adm_on)))
adm_list = admin.get("/wardrobe/items", headers=csrf(admin))
check("W4 other user's wardrobe listing does not contain shopper's item", wid is not None and all(i.get("id") != wid for i in (adm_list.json() if adm_list.status_code == 200 else [])), adm_list.status_code)
anon_get = anon.get(f"/wardrobe/items/{wid}") if wid else None
check("W5 anonymous cannot read a wardrobe item", anon_get is None or anon_get.status_code in (401, 403, 404), anon_get.status_code if anon_get else "n/a")

# ---- 7. Save-as-look via the real endpoint ----
shopper_pids = rec_product_ids(off) or [sorted(catalogue_ids)[0]]
body = {"title": "E2E Dinner Look", "occasion": "dinner", "product_ids": shopper_pids[:2], "description": "e2e"}
r = shopper.post("/outfits/save", json=body, headers=csrf(shopper))
check("S1 signed-in save returns 201 with is_saved true", r.status_code == 201 and r.json().get("is_saved") is True, (r.status_code, (r.json() or {}).get("is_saved") if r.status_code==201 else r.text[:120]))
saved_id = r.json().get("id") if r.status_code == 201 else None
lst = shopper.get("/outfits", headers=csrf(shopper))
titles = [o.get("title") for o in (lst.json() if lst.status_code == 200 and isinstance(lst.json(), list) else (lst.json().get("items", []) if lst.status_code == 200 else []))]
check("S2 saved look retrievable by the owner via GET /outfits", "E2E Dinner Look" in titles, f"{len(titles)} looks")
adm_l = admin.get("/outfits", headers=csrf(admin))
adm_titles = [o.get("title") for o in (adm_l.json() if adm_l.status_code == 200 and isinstance(adm_l.json(), list) else (adm_l.json().get("items", []) if adm_l.status_code == 200 else []))]
check("S3 other user cannot see the shopper's look", "E2E Dinner Look" not in adm_titles, "")
con = db()
def look_rows():
    return con.execute("select count(*) from outfits where title='E2E Dinner Look'").fetchone()[0]
before = look_rows()
r = anon.post("/outfits/save", json=body)
check("S4 signed-out save rejected", r.status_code in (401, 403), r.status_code)
after = look_rows()
check("S5 rejected signed-out save persisted nothing (row count unchanged)", after == before, f"before={before} after={after}")

passed = sum(1 for _, ok, _ in results if ok)
print(f"\nSUMMARY {passed}/{len(results)} passed")
json.dump([{"name": n, "ok": ok, "detail": str(dt)[:300]} for n, ok, dt in results], open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_live_api_results.json"), "w"), indent=1, ensure_ascii=False)
sys.exit(0 if passed == len(results) else 1)
