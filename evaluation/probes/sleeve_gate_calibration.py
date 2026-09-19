"""Sleeve gate v2.2 calibration cohort harness (2026-09-16, Phase 2).

Runs a genuinely fresh runtime cohort (independently generated persons A–H,
fresh flat-lay garments, plus the prior phase's runtime-unknown garments)
through the REAL production path (TestClient -> TryOnService -> live Modal
worker), capturing each layer's output BEFORE the sleeve gate decides
(capture wrapper; production behavior unchanged), then scores every layer
with the gate's own probe at change thresholds {15, 20, 25, 30}.

Outputs:
  evaluation/results/calibration_v22/<case>_L<layer>.png   (saved renders)
  evaluation/results/calibration_v22/results.json          (full evidence)

NO fixture IDs, NO benchmark references, NO production-logic changes.
Truth labels for POS/NEG live cases are finalized by agent visual
inspection of the saved renders (recorded separately; not human validation).
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

# --- live worker env ---------------------------------------------------------
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

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
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
WORKER = {
    "model": health.get("model"), "device": health.get("device"),
    "git_sha": health.get("git_sha"), "service": health.get("service"),
}
print("WORKER:", json.dumps(WORKER), flush=True)

# --- capture wrapper (behavior unchanged) ------------------------------------
CAPTURES = []
CURRENT_CID = None
_real_gate = svc.evaluate_layer_sleeves

def _du_save(data_url, path: Path) -> bytes:
    raw = base64.b64decode(data_url.split(",", 1)[1])
    path.write_bytes(raw)
    return raw

def score_layer(cid: str, layer: int, out_p: Path, in_p: Path, gar_p: Path):
    if not (out_p.exists() and in_p.exists() and gar_p.exists()):
        return None
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
    cid = CURRENT_CID
    out_p = OUTDIR / f"{cid}_L{layer}.png"
    in_p = OUTDIR / f"{cid}_L{layer}_input.png"
    gar_p = OUTDIR / f"{cid}_L{layer}_garment.png"
    cap = {"layer": layer, "product_id": product_id, "slot_type": slot_type,
           "sleeve_length": sleeve_length}
    try:
        raw_out = _du_save(output_data_url, out_p)
        raw_in = _du_save(input_data_url, in_p)
        if isinstance(garment_ref, str) and garment_ref.startswith("data:image"):
            _du_save(garment_ref, gar_p)
        cap["output_sha256"] = hashlib.sha256(raw_out).hexdigest()
        cap["input_sha256"] = hashlib.sha256(raw_in).hexdigest()
    except Exception as e:  # noqa: BLE001
        cap["capture_error"] = f"{type(e).__name__}: {str(e)[:150]}"
    raised = None
    decision = None
    try:
        decision = await _real_gate(
            slot_type=slot_type, sleeve_length=sleeve_length,
            output_data_url=output_data_url, input_data_url=input_data_url,
            garment_ref=garment_ref, product_id=product_id, layer=layer)
    except Exception as e:  # noqa: BLE001
        raised = e
        cap["gate_status"] = "REFUSE"
        cap["gate_reason"] = str(e)[:300]
    else:
        cap["gate_status"] = decision.get("status")
        cap["gate_reason"] = str(decision.get("reason"))[:300]
        cap["gate_coverage"] = decision.get("coverage")
    try:
        cap["scores"] = score_layer(cid, layer, out_p, in_p, gar_p)
    except Exception as e:  # noqa: BLE001
        cap["score_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    CAPTURES.append(cap)
    if raised is not None:
        raise raised
    return decision

svc.evaluate_layer_sleeves = capturing_gate

# --- constants -----------------------------------------------------------------
def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"
DYN = REPO / "evaluation" / "dyninputs" / "local"
DYN_G = REPO / "evaluation" / "dyninputs" / "global"
OUTDIR = REPO / "evaluation" / "results" / "calibration_v22"
OUTDIR.mkdir(parents=True, exist_ok=True)

from backend.tests.test_architecture_dynamic import _make_product

G = {
    "dark_blazer": (FRESH / "garment_dark_blazer.jpg", "outerwear", "long"),
    "black_ls":    (FRESH / "garment_black_longsleeve.jpg", "tops", "long"),
    "burgundy_ls": (ARCH / "garment_rt4.jpg", "tops", "long"),
    "teal_tee":    (ARCH / "garment_rt1.jpg", "tops", "short"),
    "olive_chinos":(ARCH / "garment_rt2.jpg", "bottoms", "none"),
    "dress":       (DYN / "garment_local_dress.jpg", "dresses", "long"),
    "arabic_tee":  (DYN / "garment_local_arabic_tee.jpg", "tops", "long"),
    "logo_blazer": (DYN_G / "garment_global_logo_blazer.jpg", "outerwear", "long"),
}
P = {k: (FRESH / f"person_{k}.jpg") for k in "ABCDEFGH"}

CASES = [
    ("cal_01", "POS", "A", [("dark_blazer", None)], {"skin": "fair", "bg": "light", "trousers": "dark", "pose": "arms_sides", "garment": "dark_blazer_fresh", "lighting": "even"}),
    ("cal_02", "POS", "B", [("burgundy_ls", None)], {"skin": "tan", "bg": "light", "trousers": "dark", "pose": "arms_sides", "garment": "dark_colored_ls", "lighting": "even"}),
    ("cal_03", "POS", "D", [("burgundy_ls", None)], {"skin": "medium", "bg": "dark", "trousers": "dark", "pose": "arms_sides", "garment": "dark_colored_ls", "lighting": "even"}),
    ("cal_04", "POS", "E", [("burgundy_ls", None)], {"skin": "fair", "bg": "light", "trousers": "dark", "pose": "arms_raised", "garment": "dark_colored_ls", "lighting": "even"}),
    ("cal_05", "POS", "H", [("burgundy_ls", None)], {"skin": "fair", "bg": "light", "trousers": "mid", "pose": "arms_sides", "garment": "dark_colored_ls", "lighting": "dim"}),
    ("cal_06", "POS", "A", [("dress", None)], {"skin": "fair", "bg": "light", "trousers": "n/a", "pose": "arms_sides", "garment": "one_piece_dress", "lighting": "even"}),
    ("cal_07", "POS", "F", [("arabic_tee", None)], {"skin": "light_medium", "bg": "light", "trousers": "dark", "pose": "arms_sides", "garment": "arabic_text_ls", "lighting": "even", "hijab": True}),
    ("cal_08", "POS", "G", [("dress", None)], {"skin": "medium", "bg": "light", "trousers": "dark", "pose": "arms_sides", "garment": "one_piece_dress", "lighting": "even"}),
    ("cal_09", "POS", "B", [("logo_blazer", None)], {"skin": "tan", "bg": "light", "trousers": "dark", "pose": "arms_sides", "garment": "logo_dark_outerwear", "lighting": "even"}),
    ("cal_10", "NEG", "B", [("teal_tee", "long")], {"skin": "tan", "bg": "light", "trousers": "dark", "pose": "arms_sides", "garment": "short_sleeve_declared_long", "lighting": "even"}),
    ("cal_11", "CTRL", "C", [("teal_tee", None)], {"skin": "deep", "bg": "light", "trousers": "light", "pose": "arms_sides", "garment": "short_sleeve_control", "lighting": "even"}),
    ("cal_12", "CTRL", "A", [("olive_chinos", None)], {"skin": "fair", "bg": "light", "trousers": "dark", "pose": "arms_sides", "garment": "lower_slot_control", "lighting": "even"}),
    ("tpb_1", "N2_TPB", "A", [("teal_tee", None), ("olive_chinos", None)], {"matrix": "person_A_top_A_bottom_A"}),
    ("tpb_2", "N2_TPB", "B", [("teal_tee", None), ("olive_chinos", None)], {"matrix": "person_B_top_A_bottom_B", "note": "same bottom garment this turn; fresh beige bottom pending image gen"}),
    ("tpb_3", "N2_TPB", "A", [("burgundy_ls", None), ("olive_chinos", None)], {"matrix": "person_A_top_B_bottom_A"}),
    ("tpb_4", "N2_TPB", "C", [("burgundy_ls", None), ("olive_chinos", None)], {"matrix": "fresh_person_C_top_B_bottom_A"}),
    ("io_1", "N2_IO", "A", [("teal_tee", None), ("dark_blazer", None)], {"matrix": "AT15_class_fresh_person_fresh_blazer"}),
    ("io_3", "N2_IO", "B", [("burgundy_ls", None), ("dark_blazer", None)], {"matrix": "fresh_inner_outer_long_inner"}),
]

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
            pid = _make_product(db, slug, f"CAL {cid} {gkey}", data_url(img), "#888888", sleeve_length=s)
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
        j = None
    detail = (j or {}).get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    entry = {
        "http": r.status_code, "elapsed_s": elapsed,
        "status": (j or {}).get("status"),
        "error_code": err.get("code"),
        "error_message": str(err.get("message", ""))[:250],
        "model_used": (j or {}).get("model_used"),
        "verification": (j or {}).get("verification"),
        "layering_order": (j or {}).get("layering_order"),
        "product_ids": ids,
        "layers": list(CAPTURES),
    }
    out_url = (j or {}).get("rendered_result_url")
    if isinstance(out_url, str) and out_url.startswith("data:"):
        final = base64.b64decode(out_url.split(",", 1)[1])
        (OUTDIR / f"{cid}_final.png").write_bytes(final)
        entry["final_output_sha256"] = hashlib.sha256(final).hexdigest()
    return entry

for cid, kind, person_key, garments, attrs in CASES:
    CAPTURES.clear()
    CURRENT_CID = cid
    try:
        entry = render_case(cid, person_key, garments)
    except Exception as e:  # noqa: BLE001
        entry = {"http": None, "error": f"{type(e).__name__}: {str(e)[:200]}", "layers": []}
    entry.update({"kind": kind, "attributes": attrs})
    RESULTS["cases"][cid] = entry
    layersum = {f"L{l['layer']}": (l.get("gate_status"),
                                   l.get("scores", {}).get("best_20") if isinstance(l.get("scores"), dict) else None)
                for l in entry.get("layers", [])}
    print(f"{cid:8} {kind:8} http={entry.get('http')} st={str(entry.get('status'))[:10]} "
          f"err={str(entry.get('error_code'))[:28]:28} {layersum}", flush=True)

# --- L1 defect artifact replay (hermetic, original 2026-09-15 render) ----------
def l1_replay():
    out_p = REPO / "evaluation" / "results" / "outputs" / "dyn_L1_local_hijab_arabic_tee.png"
    in_p = DYN / "person_local_hijab.jpg"
    gar_p = DYN / "garment_local_arabic_tee.jpg"
    if not (out_p.exists() and in_p.exists() and gar_p.exists()):
        return {"skipped": "artifact missing"}
    out_img = Image.open(out_p).convert("RGB")
    in_img = Image.open(in_p).convert("RGB")
    ref = gate_mod.garment_dominant_lab(Image.open(gar_p).convert("RGB"))
    scores = {}
    orig = gate_mod.FOREARM_CHANGE_THRESHOLD
    try:
        for t in (15.0, 20.0, 25.0, 30.0):
            gate_mod.FOREARM_CHANGE_THRESHOLD = t
            scores[str(t)] = gate_mod.forearm_garment_coverage(out_img, in_img, ref)
    finally:
        gate_mod.FOREARM_CHANGE_THRESHOLD = orig
    decision = gate_mod.evaluate_sleeves_sync(
        slot_type="upper_inner", sleeve_length="long",
        output_img=out_img, input_img=in_img, garment_img=Image.open(gar_p).convert("RGB"))
    return {"ref_lab": [round(v, 1) for v in ref], "sweep": scores,
            "best_20": max(scores["20.0"].values()),
            "gate_status": decision["status"], "gate_reason": str(decision["reason"])[:200]}

RESULTS["cases"]["l1_replay"] = {"kind": "NEG",
                                 "attributes": {"source": "original L1 defect render 2026-09-15"},
                                 **l1_replay()}
lr = RESULTS["cases"]["l1_replay"]
print(f"{'l1_replay':8} {'NEG':8} hermetic best_20={lr.get('best_20')} gate={lr.get('gate_status')}", flush=True)

(OUTDIR / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUTDIR / "results.json", flush=True)
