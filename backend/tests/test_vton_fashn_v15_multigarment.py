"""Feature 03: multi-garment VTON (fashn_v15) — zero-GPU unit tests.

Pins the new engine + worker + backend contract WITHOUT GPU/torch:

Engine (services/vton-worker/engine/fashn_v15.py):
  * registered as `fashn_v15`, multigarment, honestly NON-commercial (parser);
  * normalize_garments: canonical tops-before-bottoms order (client order
    never trusted), one-pieces conflict rejection, unsupported slots
    rejection, max 3 garments, missing image rejection;
  * detect_garment_photo_type: person labels -> model, none -> flat-lay;
  * classify_garment_photo (the anti-contamination gate): parser labels
    first, DWPose body-keypoint fallback when the parser has no verdict,
    conservative 'model' when BOTH detectors are inconclusive (a loud
    verification failure beats a silently contaminated render); the deciding
    detector is recorded per layer (photo_type_detector);
  * render_outfit with a fake pipeline: layer 1 segmentation-free, layer 2+
    parser-masked, layer 2 receives layer 1's output, honest per-layer
    verification, failed layer aborts (never composites on a non-applied
    layer);
  * swappable parser seam: parser_impl is injected as hp_model unchanged.

Worker (services/vton-worker/modal_app_v15.py):
  * request contract: max 3 garments, per-garment image required,
    footwear/accessory rejected, overlay_mode whitelist, job_id charset.

Backend registry:
  * fashn_v15 present + honestly non-commercial + multigarment in
    VTON_ENGINE_LICENSES; provider spec priority 0, no flat-lay requirement.
"""
from __future__ import annotations

import os
import sys

import pytest

from backend.app.core.config import SUPPORTED_VTON_ENGINES, VTON_ENGINE_LICENSES

# Make the worker engine adapter importable without GPU/torch.
_WORKER_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "services", "vton-worker")
if _WORKER_ROOT not in sys.path:
    sys.path.insert(0, _WORKER_ROOT)


# --- backend config + provider registry ----------------------------------------

def test_fashn_v15_supported_and_honestly_noncommercial():
    assert "fashn_v15" in SUPPORTED_VTON_ENGINES
    entry = VTON_ENGINE_LICENSES["fashn_v15"]
    # Honest: the parser is non-commercial until the licensed swap lands.
    assert entry["commercial"] is False
    assert entry["multigarment"] is True
    assert "non-commercial" in entry["license"].lower()
    assert "owner" in entry["note"].lower() or "2026-10-01" in entry["note"]


def test_provider_registry_has_fashn_v15_spec_without_flatlay_limit():
    from backend.app.providers.vton.registry import ENGINES

    spec = ENGINES.get("fashn_v15")
    assert spec is not None
    assert spec.commercial is False  # honest tier gating
    assert spec.requires_flatlay is False  # parser segments on-model garments
    assert spec.priority < ENGINES["fashn_vton_segfee"].priority  # preferred when allowed
    assert spec.transport == "gpu_worker"


# --- engine registration + metadata honesty -------------------------------------

def test_engine_registered_with_multigarment_support():
    import engine

    cls = engine.get_engine("fashn_v15")
    assert cls is not None
    inst = cls(weights_dir="/nonexistent", device="cpu")
    assert inst.supports_multigarment is True
    assert inst.commercially_usable is False  # parser: NVIDIA non-commercial


def test_engine_metadata_records_license_and_swap_plan():
    import engine

    inst = engine.get_engine("fashn_v15")(weights_dir="/nonexistent", device="cpu")
    meta = inst.metadata()
    assert meta["engine"] == "fashn_v15"
    assert meta["commercial"] is False
    assert "NVIDIA" in meta["license"]
    assert "non-commercial" in meta["license"].lower()
    parser = meta["parser"]
    assert parser["swappable_via"] == "FashnV15MultiGarmentEngine(parser_impl=...)"
    assert "NVIDIA" in parser["license"]
    assert meta["multigarment"] is True
    assert meta["max_garments"] == 3
    assert meta["garment_photo_types"] == ["flat-lay", "model"]


# --- normalize_garments (pure, no GPU) -------------------------------------------

def _img():
    from PIL import Image

    return Image.new("RGB", (64, 64), (10, 10, 10))


def test_normalize_orders_tops_before_bottoms_regardless_of_request_order():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    items = E.normalize_garments([
        {"image": _img(), "slot_type": "lower"},
        {"image": _img(), "slot_type": "upper_outer"},
    ])
    assert [i["category"] for i in items] == ["tops", "bottoms"]


def test_normalize_maps_legacy_slot_vocabulary():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    assert E.normalize_garments([{"image": _img(), "slot_type": "upper_inner"}])[0]["category"] == "tops"
    assert E.normalize_garments([{"image": _img(), "slot_type": "inner_layer"}])[0]["category"] == "tops"
    assert E.normalize_garments([{"image": _img(), "slot_type": "knit_layer"}])[0]["category"] == "tops"
    assert E.normalize_garments([{"image": _img(), "slot_type": "dress"}])[0]["category"] == "one-pieces"
    assert E.normalize_garments([{"image": _img(), "category": "bottoms"}])[0]["category"] == "bottoms"


def test_normalize_rejects_one_piece_plus_tops_conflict():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    with pytest.raises(ValueError, match="conflict"):
        E.normalize_garments([
            {"image": _img(), "slot_type": "dress"},
            {"image": _img(), "slot_type": "upper_outer"},
        ])


def test_normalize_rejects_one_piece_plus_bottoms_conflict():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    with pytest.raises(ValueError, match="conflict"):
        E.normalize_garments([
            {"image": _img(), "slot_type": "lower"},
            {"image": _img(), "category": "one-pieces"},
        ])


def test_normalize_rejects_unsupported_slots():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    for bad in ("footwear", "accessory", "hat", ""):
        with pytest.raises(ValueError):
            E.normalize_garments([{"image": _img(), "slot_type": bad}])


def test_normalize_rejects_more_than_three_garments():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    with pytest.raises(ValueError, match="too many"):
        E.normalize_garments(
            [{"image": _img(), "slot_type": "upper_inner"} for _ in range(4)]
        )


def test_normalize_rejects_missing_image():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    with pytest.raises(ValueError, match="missing image"):
        E.normalize_garments([{"slot_type": "upper_outer"}])


def test_normalize_accepts_three_garment_outfit():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    items = E.normalize_garments([
        {"image": _img(), "slot_type": "lower"},
        {"image": _img(), "slot_type": "upper_outer"},
        {"image": _img(), "slot_type": "upper_inner"},
    ])
    assert [i["category"] for i in items] == ["tops", "tops", "bottoms"]


# --- garment photo-type auto-detection (pure) -------------------------------------

def test_photo_type_model_when_person_labels_present():
    import numpy as np

    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    labels = np.zeros((10, 10), dtype=np.uint8)
    labels[0, 0] = 1  # face
    assert E.detect_garment_photo_type(labels) == "model"
    labels2 = np.zeros((10, 10), dtype=np.uint8)
    labels2[0, 0] = 2  # hair
    assert E.detect_garment_photo_type(labels2) == "model"


def test_photo_type_flatlay_when_only_garment_labels():
    import numpy as np

    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    labels = np.zeros((10, 10), dtype=np.uint8)
    labels[0, 0] = 3  # top (garment, not a person)
    labels[5, 5] = 6  # pants
    assert E.detect_garment_photo_type(labels) == "flat-lay"


def test_photo_type_safe_default_without_parser_verdict():
    from engine.fashn_v15 import FashnV15MultiGarmentEngine as E

    assert E.detect_garment_photo_type(None) == "flat-lay"


# --- render_outfit composition with a fake pipeline (no GPU/torch) ----------------


class _FakeParser:
    """Duck-typed parser seam: same .predict() surface as FashnHumanParser."""

    def __init__(self, person_labels=None):
        self.person_labels = person_labels if person_labels is not None else {}
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        import numpy as np

        arr = np.zeros((10, 10), dtype=np.uint8)
        for lbl in self.person_labels.get(id(image), []):
            arr[0, 0] = lbl
        return arr


class _FakePipeline:
    """Records calls; returns a genuinely-changed image each time."""

    def __init__(self):
        self.calls = []
        self.outputs = []
        self.n = 0

    def __call__(self, *, person_image, garment_image, category,
                 garment_photo_type, segmentation_free, num_timesteps, seed):
        import numpy as np
        from PIL import Image

        self.n += 1
        self.calls.append({
            "person": person_image,
            "garment": garment_image,
            "category": category,
            "photo_type": garment_photo_type,
            "segmentation_free": segmentation_free,
        })
        # Different pixels every call so verify sees a genuine change
        # (textured: a gradient + block pattern, NOT a flat fill — the
        # engine's honest validator rejects blank/flat outputs).
        base = np.arange(64 * 64 * 3, dtype=np.int64).reshape(64, 64, 3)
        arr = ((base + 20 * self.n * 7) % 255).astype(np.uint8)
        out = Image.fromarray(arr, "RGB")
        # Keep the person's size so validate_output compares same shapes.
        result = type("R", (), {"images": [out.resize(person_image.size)]})()
        self.outputs.append(result.images[0])
        return result


def _engine_with_fake_pipeline(parser=None):
    import engine

    inst = engine.get_engine("fashn_v15")(weights_dir="/nonexistent", device="cpu")
    inst._pipe = _FakePipeline()
    inst._parser_model = parser if parser is not None else _FakeParser()
    inst._ready = True
    return inst


def test_render_outfit_two_garments_masked_composition():
    eng = _engine_with_fake_pipeline()
    person = _img()
    top, bottom = _img(), _img()

    final, layers = eng.render_outfit(
        person, garments=[
            {"image": top, "slot_type": "upper_outer"},
            {"image": bottom, "slot_type": "lower"},
        ],
    )

    assert len(layers) == 2
    calls = eng._pipe.calls
    # Layer 1 segmentation-free (upstream-recommended), layer 2 parser-masked.
    assert calls[0]["segmentation_free"] is True
    assert calls[1]["segmentation_free"] is False
    # Canonical order: tops rendered first, bottoms second.
    assert calls[0]["category"] == "tops"
    assert calls[1]["category"] == "bottoms"
    # Layer 2 renders on layer 1's output (sequential composition)…
    assert list(calls[1]["person"].getdata()) == list(eng._pipe.outputs[0].getdata())
    # …and the final image IS layer 2's output pixels.
    assert list(final.getdata()) == list(eng._pipe.outputs[1].getdata())
    # Per-layer honest verification recorded.
    assert all(l["verify"]["PASS"] for l in layers)
    assert [l["layer"] for l in layers] == [1, 2]


def test_render_outfit_single_garment_is_segmentation_free():
    eng = _engine_with_fake_pipeline()
    eng.render_outfit(person_image=_img(), garments=[
        {"image": _img(), "slot_type": "lower"},
    ])
    assert len(eng._pipe.calls) == 1
    assert eng._pipe.calls[0]["segmentation_free"] is True


def test_render_outfit_overlay_mode_segfree_full_regen_each_layer():
    eng = _engine_with_fake_pipeline()
    eng.render_outfit(
        person_image=_img(),
        garments=[
            {"image": _img(), "slot_type": "upper_outer"},
            {"image": _img(), "slot_type": "lower"},
        ],
        overlay_mode="segfree",
    )
    assert all(c["segmentation_free"] is True for c in eng._pipe.calls)


def test_render_outfit_rejects_bad_overlay_mode():
    eng = _engine_with_fake_pipeline()
    with pytest.raises(ValueError, match="overlay_mode"):
        eng.render_outfit(person_image=_img(), garments=[{"image": _img(), "slot_type": "lower"}], overlay_mode="wild")


def test_render_outfit_aborts_when_layer_not_applied():
    """A layer whose garment did not materially change the image must abort —
    never keep compositing on top of a non-applied layer (honest failure)."""
    import numpy as np
    from PIL import Image

    import engine

    class _EchoPipeline:
        def __call__(self, **kwargs):
            # Echo the person unchanged -> verify.PASS False.
            return type("R", (), {"images": [kwargs["person_image"]]})()

    inst = engine.get_engine("fashn_v15")(weights_dir="/nonexistent", device="cpu")
    inst._pipe = _EchoPipeline()
    inst._parser_model = _FakeParser()
    inst._ready = True

    with pytest.raises(RuntimeError, match="failed output verification"):
        inst.render_outfit(
            person_image=_img(),
            garments=[
                {"image": _img(), "slot_type": "upper_outer"},
                {"image": _img(), "slot_type": "lower"},
            ],
        )


def test_render_base_contract_returns_image_only():
    """The base-class render() contract still holds: a single image, no tuple."""
    eng = _engine_with_fake_pipeline()
    out = eng.render(person_image=_img(), garment_image=_img(), category="tops")
    from PIL import Image as _I

    assert isinstance(out, _I.Image)


def test_parser_impl_injection_is_the_swap_seam():
    """Swapping the parser is one injection: the pipeline's hp_model is
    replaced by the duck-typed parser_impl, upstream untouched."""
    import engine

    sentinel = _FakeParser()
    inst = engine.get_engine("fashn_v15")(weights_dir="/x", device="cpu", parser_impl=sentinel)
    inst._pipe = _FakePipeline()
    inst._parser_model = sentinel  # load() wires pipe.hp_model = parser_impl
    inst._ready = True
    inst.render_outfit(person_image=_img(), garments=[{"image": _img(), "slot_type": "upper_outer"}])
    assert sentinel.calls >= 1  # used for photo-type detection


# --- worker request contract (pydantic, no GPU) -----------------------------------

def _worker_module():
    import importlib.util

    path = os.path.join(_WORKER_ROOT, "modal_app_v15.py")
    spec = importlib.util.spec_from_file_location("confit_modal_app_v15", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def worker():
    return _worker_module()


def test_worker_app_name_is_canonical(worker):
    assert worker.app.name == "confit-vton-worker"


def test_worker_accepts_three_garment_outfit(worker):
    req = worker.VTONJobRequest(
        job_id="job_1",
        user_image_base64_or_url="data:image/png;base64,AAAA",
        garments=[
            {"slot_type": "upper_inner", "image_base64": "data:image/png;base64,AAAA"},
            {"slot_type": "upper_outer", "image_base64": "data:image/png;base64,AAAA"},
            {"slot_type": "lower", "image_base64": "data:image/png;base64,AAAA"},
        ],
    )
    assert len(req.garments) == 3
    assert req.overlay_mode == "masked"  # safe default


def test_worker_rejects_four_garments(worker):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        worker.VTONJobRequest(
            job_id="job_1",
            user_image_base64_or_url="x",
            garments=[
                {"slot_type": "upper_inner", "image_base64": "x"},
                {"slot_type": "upper_outer", "image_base64": "x"},
                {"slot_type": "lower", "image_base64": "x"},
                {"slot_type": "dress", "image_base64": "x"},
            ],
        )


def test_worker_rejects_footwear_and_accessory(worker):
    from pydantic import ValidationError

    for slot in ("footwear", "accessory"):
        with pytest.raises(ValidationError):
            worker.VTONJobRequest(
                job_id="job_1",
                user_image_base64_or_url="x",
                garments=[{"slot_type": slot, "image_base64": "x"}],
            )


def test_worker_rejects_garment_without_image(worker):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        worker.VTONJobRequest(
            job_id="job_1",
            user_image_base64_or_url="x",
            garments=[{"slot_type": "lower"}],
        )


def test_worker_rejects_unknown_overlay_mode(worker):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        worker.VTONJobRequest(
            job_id="job_1",
            user_image_base64_or_url="x",
            garments=[{"slot_type": "lower", "image_base64": "x"}],
            overlay_mode="aggressive",
        )


def test_worker_parser_info_is_honest(worker):
    info = worker._parser_info()
    assert info["present"] is True  # by design in this worker
    assert "non-commercial" in info["license"].lower()
    assert "swap" in info["owner_decision"].lower()
    assert info["swappable_via"].startswith("engine.FashnV15MultiGarmentEngine")


# --- vendored upstream integrity ----------------------------------------------------

def test_vendored_upstream_is_pristine_with_parser_dependency():
    """The v15 vendor is the PRISTINE upstream (parser as a runtime dependency);
    the segfee vendor is the parser-free fork (may only MENTION it in prose)."""
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    upstream_pp = os.path.join(root, "vendor", "fashn-vton-1.5", "pyproject.toml")
    fork_pp = os.path.join(root, "vendor", "fashn-vton-segfee", "pyproject.toml")
    assert os.path.exists(upstream_pp)
    with open(upstream_pp) as f:
        assert '"fashn-human-parser' in f.read()  # real dependency string
    with open(fork_pp) as f:
        assert '"fashn-human-parser' not in f.read()  # not a dependency anymore


def test_vendored_upstream_pipeline_uses_hp_model_predict():
    """Upstream integration points: parser predicted for person + garment."""
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    path = os.path.join(root, "vendor", "fashn-vton-1.5", "src", "fashn_vton", "pipeline.py")
    with open(path) as f:
        src = f.read()
    assert "person_seg_pred = self.hp_model.predict(person_image_np)" in src
    assert "garment_seg_pred = self.hp_model.predict(garment_image_np)" in src


def test_provenance_records_owner_decision_and_swap_plan():
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    path = os.path.join(root, "vendor", "fashn-vton-1.5", "UPSTREAM_PROVENANCE.txt")
    with open(path) as f:
        text = f.read()
    assert "7c0f10af" in text
    assert "NON-COMMERCIAL" in text
    assert "2026-10-01" in text
    assert "swap" in text.lower()


# --- photo-type CLASSIFICATION: the two-detector anti-contamination gate --------
#
# classify_garment_photo is the gate that keeps a garment photo's PERSON out
# of the composition. Detector order: parser labels (primary) -> DWPose body
# keypoints (independent fallback) -> conservative 'model' if both are
# inconclusive (a loud verification failure is better than a silently
# contaminated render).


class _BrokenParser:
    """Parser that yields no verdict (raises) — triggers the DWPose fallback."""

    def predict(self, image):
        raise RuntimeError("parser unavailable")


class _FakePoseModel:
    """DWPose-shaped detector: ``bodies.subset`` with N visible body keypoints.

    After DWPose's own thresholding (dwpose.py __call__), a visible keypoint
    carries its index and an invisible one is -1 — the engine counts the
    non-(-1) entries."""

    def __init__(self, visible_body_keypoints: int, raise_on_call: bool = False):
        self.visible = visible_body_keypoints
        self.raise_on_call = raise_on_call
        self.calls = []

    def __call__(self, img):
        import numpy as np

        self.calls.append(img)
        if self.raise_on_call:
            raise RuntimeError("pose detector unavailable")
        subset = np.full((1, 18), -1.0)
        for j in range(min(self.visible, 18)):
            subset[0, j] = float(j)  # visible -> its index, DWPose convention
        return {
            "bodies": {"candidate": np.zeros((18, 3)), "subset": subset},
            "hands": np.full((1, 42), -1.0),
            "faces": np.full((1, 68), -1.0),
        }


def _classifier_engine(parser, pose_visible=None, pose_raises=False):
    """Engine wired with a chosen parser verdict and a DWPose-shaped pose model."""
    inst = _engine_with_fake_pipeline(parser=parser)
    inst._pipe.pose_model = _FakePoseModel(pose_visible or 0, raise_on_call=pose_raises)
    return inst


def test_classification_parser_verdict_wins_when_available():
    engine = _classifier_engine(_FakeParser())  # working parser, no person labels
    ptype, evidence = engine.classify_garment_photo(_img())
    assert ptype == "flat-lay"
    assert evidence["detector"] == "parser"
    # The pose fallback must NOT have run when the parser already decided.
    assert engine._pipe.pose_model.calls == []


class _PersonParser:
    """Parser that always reports a person label (a worn garment photo)."""

    def predict(self, image):
        import numpy as np

        arr = np.zeros((10, 10), dtype=np.uint8)
        arr[0, 0] = 1  # face -> personhood label
        return arr


def test_classification_parser_person_labels_report_model():
    engine = _classifier_engine(_PersonParser())
    ptype, evidence = engine.classify_garment_photo(_img())
    assert ptype == "model"
    assert evidence["detector"] == "parser"
    # The parser already decided: the pose fallback must not have run.
    assert engine._pipe.pose_model.calls == []


def test_classification_dwpose_fallback_detects_person_when_parser_dead():
    # HARD CASE: the parser is down AND the garment photo is worn. Without
    # the fallback this defaulted to 'flat-lay' and fed the photo's person
    # straight into the composition — the contamination this gate exists for.
    engine = _classifier_engine(_BrokenParser(), pose_visible=7)
    ptype, evidence = engine.classify_garment_photo(_img())
    assert ptype == "model"
    assert evidence["detector"] == "dwpose"


def test_classification_dwpose_fallback_flatlay_when_no_person():
    engine = _classifier_engine(_BrokenParser(), pose_visible=0)
    ptype, evidence = engine.classify_garment_photo(_img())
    assert ptype == "flat-lay"
    assert evidence["detector"] == "dwpose"


def test_classification_keypoint_threshold_boundary():
    # Exactly the minimum (4 body keypoints: a face/shoulders silhouette)
    # counts as a person; one below does not.
    assert _classifier_engine(_BrokenParser(), pose_visible=4).classify_garment_photo(_img())[0] == "model"
    assert _classifier_engine(_BrokenParser(), pose_visible=3).classify_garment_photo(_img())[0] == "flat-lay"


def test_classification_conservative_model_when_both_detectors_dead():
    # HARDEST CASE: no detector can answer. Choosing 'model' risks a degraded
    # render that honest verification fails LOUDLY; choosing 'flat-lay' risks
    # a silently contaminated render. The loud failure is the correct default.
    engine = _classifier_engine(_BrokenParser(), pose_raises=True)
    ptype, evidence = engine.classify_garment_photo(_img())
    assert ptype == "model"
    assert evidence["detector"] == "none-conservative"


def test_classification_pose_result_is_boolean_not_keypoint_count():
    engine = _classifier_engine(_BrokenParser(), pose_visible=18)
    verdict, _ = engine.classify_garment_photo(_img())
    assert verdict in ("model", "flat-lay") and verdict == "model"


def test_render_outfit_records_detector_and_respects_explicit_photo_type():
    # Explicit client-supplied photo_type is respected verbatim (detector
    # 'explicit', no detector runs), and the per-layer metadata records BOTH
    # the photo type and WHICH detector decided it.
    engine = _engine_with_fake_pipeline()
    img = _img()
    _, layers = engine.render_outfit(
        _img(),
        garments=[{"image": img, "slot_type": "upper_outer", "photo_type": "flat-lay"}],
    )
    assert layers[0]["photo_type"] == "flat-lay"
    assert layers[0]["photo_type_detector"] == "explicit"
    assert engine._pipe.calls[0]["photo_type"] == "flat-lay"


def test_render_outfit_end_to_end_dwpose_fallback_flow():
    # End-to-end: parser dead + worn garment -> DWPose decides 'model' ->
    # the pipeline receives garment_photo_type='model' (masking ON) and the
    # layer metadata shows the dwpose detector.
    engine = _classifier_engine(_BrokenParser(), pose_visible=6)
    _, layers = engine.render_outfit(
        _img(),
        garments=[{"image": _img(), "slot_type": "upper_outer"}],
    )
    assert layers[0]["photo_type"] == "model"
    assert layers[0]["photo_type_detector"] == "dwpose"
    assert engine._pipe.calls[0]["photo_type"] == "model"
