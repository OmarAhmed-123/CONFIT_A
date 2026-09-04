"""Contract gate for the CANONICAL COMMERCIAL production worker.

The production path is the COMMERCIAL segmentation-free FASHN engine
(`fashn_vton_segfee`, deployed as `services/vton-worker/modal_app_segfee.py`).
This gate pins the properties that make the deployed worker commercially
defensible and free of the non-commercial CatVTON / human-parser path:

  * the worker renders through the engine ADAPTER (`engine.get_engine`) —
    no diffusion code, no CatVTON, no rembg, no human-parser in the runtime;
  * `VTONJobRequest` + `/process` uses the SAME external contract as the rest of
    CONFIT (X-VTON-Admin auth, rendered_image_data_url, model_used, verify),
    so the API service and frontend need no change;
  * the engine is single-category — the worker REJECTS multi-garment requests
    instead of naively compositing;
  * the worker surfaces health/readiness with honest model_loaded semantics and
    FAILS LOUDLY if the restricted human-parser is present in the runtime.
"""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKER = REPO / "services" / "vton-worker" / "modal_app_segfee.py"
ENGINE = REPO / "services" / "vton-worker" / "engine"
CATVTON_WORKER = REPO / "services" / "vton-worker" / "modal_app.py"

# SLOT_TYPE v1 vocabulary -> FASHN category. The commercial engine supports only
# tops / bottoms / one-pieces; unsupported slots must map to None (INPUT_INVALID).
SLOT_TO_CATEGORY = {
    "upper_outer": "tops",
    "upper_inner": "tops",
    "lower": "bottoms",
    "dress": "one-pieces",
    "footwear": None,
    "accessory": None,
}


class TestCommercialWorkerIsCanonical:
    def test_worker_file_exists(self):
        assert WORKER.exists(), "canonical commercial worker must exist"

    def test_worker_uses_engine_adapter_not_diffusion(self):
        src = WORKER.read_text()
        # Must resolve the engine through the adapter (single canonical interface), not
        # call a diffusion pipeline directly in the worker.
        assert "from engine import get_engine" in src
        assert "get_engine(\"fashn_vton_segfee\")" in src

    def test_commercial_engine_declared(self):
        src = WORKER.read_text()
        assert '"engine": "fashn_vton_segfee"' in src
        assert '"commercial": True' in src
        assert '"model_used"' in src

    def test_no_catvton_or_rembg_in_runtime(self):
        src = WORKER.read_text()
        # The commercial engine is segmentation-free; CatVTON / rembg must not appear
        # as a runtime dependency (comments/documentation are allowed, imports are not).
        # We assert strong signals: no `from rembg`, no `CatVTONPipeline`, no mask calls.
        assert "from rembg" not in src
        assert "CatVTONPipeline" not in src
        assert "AgnosticMaskGenerator" not in src
        assert "create_agnostic_mask" not in src
        # The worker delegates to the engine adapter, which enforces the fork's
        # segmentation-free + flat-lay envelope (that enforcement lives in the
        # adapter/fork, not the worker source).
        assert "from engine import get_engine" in src

    def test_parser_cannot_load_in_runtime(self):
        # The worker must abort a job if the restricted human-parser is somehow present.
        src = WORKER.read_text()
        assert "def _parser_in_runtime" in src
        assert "fashn_human_parser" in src

    def test_single_garment_enforced(self):
        # FASHN is single-category; the worker must reject naive multi-garment requests.
        src = WORKER.read_text()
        assert "MAX_GARMENTS = 1" in src
        assert "is single-category" in src
        assert "len(garments) != 1" in src or "len(garments) > 1" in src

    def test_slot_to_category_mapping(self):
        import ast as _ast
        tree = _ast.parse(WORKER.read_text())
        mapping = None
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Assign):
                for t in node.targets:
                    if isinstance(t, _ast.Name) and t.id == "SLOT_TO_CATEGORY":
                        mapping = _ast.literal_eval(node.value)
        assert mapping is not None, "SLOT_TO_CATEGORY must be defined"
        assert mapping == SLOT_TO_CATEGORY, mapping

    def test_contract_preserved(self):
        # Same external contract as the rest of CONFIT.
        src = WORKER.read_text()
        assert "@modal.fastapi_endpoint" in src
        assert "X-VTON-Admin" in src
        assert "CONFIT_WORKER_ADMIN_TOKEN" in src
        assert "rendered_image_data_url" in src
        assert "status_code=401" in src  # auth failure -> 401, never bypassed
        assert "status_code=503" in src  # engine unavailable / not ready -> 503


class TestEngineAdapterContract:
    def test_adapter_is_commercial_and_single_category(self):
        # Insert the worker dir (so `engine` resolves to services/vton-worker/engine).
        sys_path_patch = __import__("sys").path.copy()
        __import__("sys").path.insert(0, str(ENGINE.parent))
        try:
            from engine import get_engine

            cls = get_engine("fashn_vton_segfee")
            assert cls is not None
            assert cls.name == "fashn_vton_segfee"
            assert cls.commercially_usable is True
            assert cls.supports_multigarment is False  # single-category
            assert cls._VENDOR_PATH == "/root/fashn-vton-segfee"
            # metadata is honest
            meta = cls(weights_dir="/tmp", device="cpu").metadata()
            assert meta["engine"] == "fashn_vton_segfee"
            assert meta["commercial"] is True
            assert "human-parser" in meta["license"]
        finally:
            __import__("sys").path = sys_path_patch


class TestSingleProductionPath:
    def test_catvton_worker_is_not_the_declared_deployment(self):
        # The deployment contract must point at the commercial worker, not CatVTON.
        contract = REPO / "docs" / "PRODUCTION_DEPLOYMENT_CONTRACT.md"
        assert contract.exists()
        text = contract.read_text()
        assert "modal_app_segfee.py" in text
