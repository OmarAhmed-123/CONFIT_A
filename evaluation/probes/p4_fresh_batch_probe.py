"""Phase-4 sleeve expansion + fresh local/global batch (2026-09-16).

P3-A: remaining fresh garment — black_joggers on C (light lower-body) and
     B (dark lower-body), single layer.
P4 local (fresh persons J, K generated this phase):
     J (hijab) + modest tunic; J + multicolor Arabic tee #2;
     K (modest man) + rust LS; K + black LS.
P5 global (fresh persons L, M + N=2):
     L (plus-size) + gray LS; M (East Asian, warm bg) + dark blazer;
     L + rust LS + beige chino (N=2 top+bottom);
     M + black LS + dark blazer (N=2 inner+outer, class-C variant).

Production path; capture wrapper preserves production semantics and saves
layer input/output artifacts for agent visual inspection (hijab
preservation, text fidelity, application quality).
"""
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend" / "tests"))
sys.path.insert(0, str(REPO / "evaluation"))

urls = (REPO / "evaluation" / ".eval_urls").read_text().split()
env_text = (REPO / "evaluation" / ".eval_env").read_text()
token = re.search(r"^VTON_EVAL_ADMIN_TOKEN=(.+)$", env_text, re.M).group(1).strip()
os.environ["VTON_WORKER_URL"] = urls[1]
os.environ["VTON_WORKER_PROCESS_URL"] = urls[1]
os.environ["VTON_WORKER_HEALTH_URL"] = urls[0]
os.environ["VTON_WORKER_READINESS_URL"] = urls[0]
os.environ["VTON_WORKER_ADMIN_TOKEN"] = token
os.environ.setdefault("CONFIT_VTON_DISABLE_REMBG", "1")
os.chdir(REPO)

import httpx
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import get_db, engine as app_engine
from backend.app.seed_data import seed_database
from backend.app.main import app

TEST_DB_URL = "sqlite:///./backend/data/confit_p4_test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
app.state.limiter.enabled = False
seed_database(target_engine=test_engine, force=True)
seed_database(target_engine=app_engine, force=True)

import backend.app.services.vton_sleeve_gate as gate_mod
import backend.app.services.tryon_service as svc

health = httpx.get(urls[0], headers={"X-VTON-Admin": token}, timeout=60).json()
WORKER = {"model": health.get("model"), "device": health.get("device"),
          "git_sha": health.get("git_sha"), "service": health.get("service")}
print("WORKER:", json.dumps(WORKER), flush=True)

OUT = REPO / "evaluation" / "results" / "p4_fresh_batch"
OUT.mkdir(parents=True, exist_ok=True)

CAPTURES = []
CURRENT = None
_real_gate = svc.evaluate_layer_sleeves

def score_layer(cid, layer, out_p, in_p, gar_p):
    out_img = Image.open(out_p).convert("RGB")
    in_img = Image.open(in_p).convert("RGB")
    ref = gate_mod.garment_dominant_lab(Image.open(gar_p).convert("RGB"))
    if ref == (0.0, 0.0, 0.0):
        return {"degenerate_color": True}
    scores = {}
    orig = gate_mod.FOREARM_CHANGE_THRESHOLD
    try:
        for t in (15.0, 20.0, 25.0, 30.0):
            gate_mod.FOREARM_CHANGE_THRESHOLD = t
            scores[str(t)] = gate_mod.forearm_garment_coverage(out_img, in_img, ref)
    finally:
        gate_mod.FOREARM_CHANGE_THRESHOLD = orig
    return {"ref_lab": [round(v, 1) for v in ref], "sweep": scores,
            "best_20": max(scores["20.0"].values())}

async def capturing_gate(*, slot_type, sleeve_length, output_data_url,
                         input_data_url, garment_ref, product_id=None, layer=None):
    cid = CURRENT
    out_p = OUT / f"{cid}_L{layer}.png"
    in_p = OUT / f"{cid}_L{layer}_input.png"
    gar_p = OUT / f"{cid}_L{layer}_garment.png"
    cap = {"layer": layer, "product_id": product_id, "slot_type": slot_type,
           "sleeve_length": sleeve_length}
    try:
        raw_out = base64.b64decode(output_data_url.split(",", 1)[1])
        out_p.write_bytes(raw_out)
        in_p.write_bytes(base64.b64decode(input_data_url.split(",", 1)[1]))
        if isinstance(garment_ref, str) and garment_ref.startswith("data:image"):
            gar_p.write_bytes(base64.b64decode(garment_ref.split(",", 1)[1]))
        cap["output_sha256"] = hashlib.sha256(raw_out).hexdigest()
    except Exception as e:  # noqa: BLE001
        cap["capture_error"] = f"{type(e).__name__}: {str(e)[:150]}"
    raised = None
    try:
        decision = await _real_gate(slot_type=slot_type, sleeve_length=sleeve_length,
                                    output_data_url=output_data_url,
                                    input_data_url=input_data_url,
                                    garment_ref=garment_ref, product_id=product_id,
                                    layer=layer)
        cap["gate_status"] = decision.get("status")
        cap["gate_reason"] = str(decision.get("reason"))[:300]
        cap["gate_coverage"] = decision.get("coverage")
    except Exception as e:  # noqa: BLE001
        raised = e
        cap["gate_status"] = "REFUSE"
        cap["gate_reason"] = str(e)[:300]
    try:
        cap["scores"] = score_layer(cid, layer, out_p, in_p, gar_p)
    except Exception as e:  # noqa: BLE001
        cap["score_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    CAPTURES.append(cap)
    if raised is not None:
        raise raised
    return decision

svc.evaluate_layer_sleeves = capturing_gate

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

FRESH = REPO / "evaluation" / "dyninputs_fresh"
DYN = REPO / "evaluation" / "dyninputs" / "local"
P = {k: (FRESH / f"person_{k}.jpg") for k in "ABCDEFGHIJKLM"}
G = {
    "black_joggers": (FRESH / "garment_black_joggers.jpg", "bottoms", "none"),
    "tunic":         (FRESH / "garment_modest_tunic.jpg", "dresses", "long"),
    "arabic2":       (FRESH / "garment_arabic_tee_2.jpg", "tops", "long"),
    "rust_ls":       (FRESH / "garment_rust_longsleeve.jpg", "tops", "long"),
    "black_ls":      (FRESH / "garment_black_longsleeve.jpg", "tops", "long"),
    "gray_ls":       (FRESH / "garment_gray_longsleeve.jpg", "tops", "long"),
    "dark_blazer":   (FRESH / "garment_dark_blazer.jpg", "outerwear", "long"),
    "beige_chino":   (FRESH / "garment_beige_chino.jpg", "bottoms", "none"),
}

CASES = [
    ("p3a_c_blackjog", "P3-A", "C", [("black_joggers", None)], {}),
    ("p3a_b_blackjog", "P3-A", "B", [("black_joggers", None)], {}),
    ("p4_j_tunic",     "P4_local", "J", [("tunic", None)], {"hijab": True}),
    ("p4_j_arabic2",   "P4_local", "J", [("arabic2", None)], {"hijab": True, "multicolor": True, "arabic_text": 2}),
    ("p4_k_rust",      "P4_local", "K", [("rust_ls", None)], {"modest_man": True}),
    ("p4_k_black",     "P4_local", "K", [("black_ls", None)], {"modest_man": True}),
    ("p5_l_gray",      "P5_global", "L", [("gray_ls", None)], {"plus_size": True}),
    ("p5_m_blazer",    "P5_global", "M", [("dark_blazer", None)], {"warm_bg": True}),
    ("p5_l_tpb",       "P5_N2_TPB", "L", [("rust_ls", None), ("beige_chino", None)], {}),
    ("p5_m_io",        "P5_N2_IO", "M", [("black_ls", None), ("dark_blazer", None)], {"classC_variant": True}),
]

from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

RESULTS = {"worker": WORKER, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cases": {}}

def render_case(cid, person_key, garments):
    db = TestingSessionLocal()
    try:
        ids = []
        for gkey, declared in garments:
            img, slug, default_sleeve = G[gkey]
            s = declared if declared is not None else default_sleeve
            pid = _make_product(db, slug, f"P4 {cid} {gkey}", data_url(img), "#888888", sleeve_length=s)
            ids.append(pid)
    finally:
        db.close()
    person = base64.b64encode(P[person_key].read_bytes()).decode()
    t0 = time.time()
    r = client.post("/api/v1/tryon/multi-render",
                    json={"product_ids": ids, "user_image_base64": person,
                          "avatar_model_id": None, "gender_mode": "infer_from_image"})
    elapsed = round(time.time() - t0, 1)
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        j = {}
    detail = j.get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    entry = {"http": r.status_code, "elapsed_s": elapsed, "status": j.get("status"),
             "error_code": err.get("code"), "error_message": str(err.get("message", ""))[:250],
             "layers": [dict(c) for c in CAPTURES]}
    out_url = j.get("rendered_result_url") or j.get("result_image_data_url")
    if isinstance(out_url, str) and out_url.startswith("data:"):
        final = base64.b64decode(out_url.split(",", 1)[1])
        (OUT / f"{cid}_final.png").write_bytes(final)
        entry["final_sha256"] = hashlib.sha256(final).hexdigest()
    return entry

for cid, kind, person_key, garments, attrs in CASES:
    CAPTURES.clear()
    CURRENT = cid
    try:
        entry = render_case(cid, person_key, garments)
    except Exception as e:  # noqa: BLE001
        entry = {"http": None, "error": f"{type(e).__name__}: {str(e)[:200]}", "layers": []}
    entry.update({"kind": kind, "person": person_key, "attributes": attrs})
    RESULTS["cases"][cid] = entry
    layersum = {f"L{l['layer']}": (l.get("gate_status"),
                                   l.get("scores", {}).get("best_20") if isinstance(l.get("scores"), dict) else None)
                for l in entry.get("layers", [])}
    print(f"{cid:16} {kind:10} http={entry.get('http')} err={str(entry.get('error_code'))[:26]:26} {layersum}", flush=True)

(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "results.json", flush=True)
