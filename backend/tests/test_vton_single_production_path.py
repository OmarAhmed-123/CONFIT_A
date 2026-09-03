"""VTON architecture gate — one authoritative production path, no reachable placeholder.

Final release gate findings this locks down:

1. DUPLICATE IMPLEMENTATIONS. The repo shipped TWO VTON implementations:
     * modal_app.py  — real CatVTON diffusion on Modal (authoritative)
     * worker.py + pipeline/vton_engine.py — CPU "geometric warp + composite"
       that ran NO diffusion yet returned status="completed", and which the
       service Dockerfile launched via CMD ["python", "worker.py"].
   The placeholder has been deleted.

2. DUPLICATE MASKING. modal_app.py carried its own rectangle mask generator, so
   the deployed worker did not run the segmentation code the tests exercised.
   It now delegates to pipeline.segmentation.AgnosticMaskGenerator.

3. MASK POLARITY. Upstream CatVTON computes `masked_image = image * (mask < 0.5)`,
   so WHITE = regenerate. The deleted rectangle implementation filled the garment
   region BLACK, i.e. it asked the model to preserve the garment and regenerate
   the background.

4. NO SILENT SUBSTITUTE OUTPUT. When real inference is unavailable the stack must
   surface VTON_ENGINE_UNAVAILABLE, never the input photo dressed up as a result.
"""

import os
import pathlib
import re

import pytest


REPO = pathlib.Path(__file__).resolve().parents[2]
MODAL_APP = REPO / "services" / "vton-worker" / "modal_app.py"
PIPELINE = REPO / "services" / "vton-worker" / "pipeline"


class TestExactlyOneVTONImplementation:
    def test_legacy_placeholder_worker_deleted(self):
        assert not (REPO / "services" / "vton-worker" / "worker.py").exists()

    @pytest.mark.parametrize("mod", ["vton_engine", "pose", "harmonization", "quality"])
    def test_placeholder_pipeline_modules_deleted(self, mod):
        assert not (PIPELINE / f"{mod}.py").exists()

    def test_no_module_claims_completed_without_diffusion(self):
        """No EXECUTABLE code may report a finished try-on from a warp/composite.

        Strings/comments are stripped so that documentation of the removed
        placeholder does not trip the scan.
        """
        import ast as _ast

        def code_only(path):
            tree = _ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Constant) and isinstance(node.value, str):
                    node.value = ""
            return _ast.unparse(tree)

        offenders = []
        for f in (REPO / "services").rglob("*.py"):
            if "_bundled_catvton" in f.as_posix():
                continue
            try:
                src = code_only(f)
            except SyntaxError:
                continue
            low = src.lower()
            if "completed" in low and ("geometric warp" in low or "composite" in low):
                offenders.append(f.as_posix())
        assert offenders == [], offenders

    def test_single_agnostic_mask_generator(self):
        hits = [f.as_posix() for f in (REPO / "services").rglob("*.py")
                if "_bundled_catvton" not in f.as_posix()
                and "def create_agnostic_mask" in f.read_text(encoding="utf-8", errors="ignore")]
        assert hits == ["services/vton-worker/pipeline/segmentation.py"] or \
               all(h.endswith("pipeline/segmentation.py") for h in hits), hits
        assert len(hits) == 1

    def test_pipeline_package_exports_only_canonical_engines(self):
        import services  # noqa: F401  (namespace check is via filesystem below)
        src = (PIPELINE / "__init__.py").read_text()
        import ast as _ast
        imported = set()
        for node in _ast.walk(_ast.parse(src)):
            if isinstance(node, _ast.ImportFrom):
                imported.update(a.name for a in node.names)
        assert imported == {"HumanParsingEngine", "AgnosticMaskGenerator",
                            "GarmentPreprocessor"}, imported


class TestDeployedWorkerCannotBeShadowed:
    def test_dockerfile_has_no_vton_server_command(self):
        df = (REPO / "services" / "vton-worker" / "Dockerfile").read_text()
        assert not re.search(r'^\s*CMD\s*\[\s*"python"\s*,\s*"worker\.py"\s*\]', df, re.M)
        assert "does not serve VTON" in df

    def test_no_deployment_config_references_placeholder(self):
        for name in ("docker-compose.yml", "Procfile", "vercel.json"):
            p = REPO / name
            if p.exists():
                assert "vton-worker/worker.py" not in p.read_text()

    def test_modal_is_the_only_declared_vton_app(self):
        src = MODAL_APP.read_text()
        assert 'modal.App("confit-vton-worker")' in src
        assert "@modal.fastapi_endpoint" in src


class TestMaskingDelegationAndPolarity:
    def test_modal_app_delegates_to_canonical_engine(self):
        src = MODAL_APP.read_text()
        assert "from pipeline.segmentation import AgnosticMaskGenerator" in src
        assert "AgnosticMaskGenerator.create_agnostic_mask(person, slot)" in src

    def test_modal_app_draws_no_masks_itself(self):
        src = MODAL_APP.read_text()
        assert "d.rectangle(" not in src
        assert "ImageDraw" not in src

    def test_segmentation_is_shipped_and_rembg_installed_in_image(self):
        src = MODAL_APP.read_text()
        assert "add_local_dir(" in src, "pipeline/ must be added to the Modal image"
        assert "rembg" in src, "rembg must be installed in the Modal image"

    def test_polarity_white_is_regenerate(self):
        """AgnosticMaskGenerator must mark the SLOT region white."""
        pytest.importorskip("numpy")
        import numpy as np
        import sys
        sys.path.insert(0, (REPO / "services" / "vton-worker").as_posix())
        from PIL import Image, ImageDraw
        from pipeline.segmentation import AgnosticMaskGenerator

        img = Image.new("RGB", (256, 384), (235, 235, 240))
        d = ImageDraw.Draw(img)
        d.ellipse((108, 30, 148, 78), fill=(200, 170, 140))
        d.rectangle((92, 80, 164, 240), fill=(60, 80, 140))
        d.rectangle((100, 240, 156, 350), fill=(40, 40, 60))

        lower = np.asarray(AgnosticMaskGenerator.create_agnostic_mask(img, "lower"))
        h = lower.shape[0]
        legs = (lower[int(0.60 * h):int(0.90 * h)] > 128).mean()
        chest = (lower[int(0.15 * h):int(0.35 * h)] > 128).mean()
        assert legs > chest, "lower-slot mask must mark LEGS white, not the chest"

    def test_upstream_polarity_documented(self):
        src = MODAL_APP.read_text()
        assert "mask < 0.5" in src, "upstream polarity contract must be documented at the call site"


class TestSegmentationResourceSafety:
    """rembg previously created a ~176MB ONNX session per mask call."""

    def test_session_is_process_cached(self):
        src = (PIPELINE / "segmentation.py").read_text()
        assert "_REMBG_SESSION" in src
        assert "def _get_rembg_session" in src
        body = src[src.index("def _try_rembg_person_mask"):]
        assert "new_session(" not in body, "session must not be created per request"

    def test_parse_results_are_cached_per_image(self):
        src = (PIPELINE / "segmentation.py").read_text()
        assert "_parse_cache" in src

    def test_multi_garment_masking_reuses_one_parse(self):
        import sys
        sys.path.insert(0, (REPO / "services" / "vton-worker").as_posix())
        from PIL import Image
        from pipeline.segmentation import HumanParsingEngine, AgnosticMaskGenerator

        img = Image.new("RGB", (128, 192), (200, 200, 205))
        calls = {"n": 0}
        original = HumanParsingEngine._parse_human_image_uncached

        def counting(image):
            calls["n"] += 1
            return original(image)

        HumanParsingEngine._parse_cache.clear()
        HumanParsingEngine._parse_human_image_uncached = staticmethod(counting)
        try:
            for slot in ("upper_inner", "upper_outer", "lower", "footwear", "accessory"):
                AgnosticMaskGenerator.create_agnostic_mask(img, slot)
        finally:
            HumanParsingEngine._parse_human_image_uncached = staticmethod(original)
            HumanParsingEngine._parse_cache.clear()

        assert calls["n"] == 1, f"segmentation ran {calls['n']}x for one person image"

    def test_degenerate_segmentation_is_rejected(self):
        src = (PIPELINE / "segmentation.py").read_text()
        assert "MIN_PERSON_COVERAGE" in src and "MAX_PERSON_COVERAGE" in src

    def test_fallback_is_reported_honestly(self):
        import sys
        sys.path.insert(0, (REPO / "services" / "vton-worker").as_posix())
        from PIL import Image
        from pipeline.segmentation import HumanParsingEngine
        HumanParsingEngine._parse_cache.clear()
        # Flat image: no person -> must fall back and SAY so
        res = HumanParsingEngine.parse_human_image(Image.new("RGB", (96, 144), (255, 255, 255)))
        assert res["fallback_used"] is True
        assert "fallback" in res["engine"]
        HumanParsingEngine._parse_cache.clear()


class TestNoSubstituteOutputEverReturnedAsSuccess:
    def test_provider_refuses_to_invent_a_render(self):
        src = (REPO / "backend" / "app" / "providers" / "tryon_provider.py").read_text()
        assert "TryOnEngineUnavailableError" in src
        assert "Never returns a substitute, cached, or placeholder image" in src

    def test_service_rejects_worker_echo(self):
        src = (REPO / "backend" / "app" / "services" / "tryon_service.py").read_text()
        assert "VTON_OUTPUT_INVALID" in src
        assert "rendered == person_image" in src

    def test_only_engine_unavailable_falls_back(self):
        """Auth/timeout/invalid-input must NOT silently degrade."""
        src = (REPO / "backend" / "app" / "services" / "tryon_service.py").read_text()
        assert 'if "VTON_ENGINE_UNAVAILABLE" in error_str' in src

    def test_worker_returns_503_when_model_not_loaded(self):
        src = MODAL_APP.read_text()
        assert "VTON_ENGINE_UNAVAILABLE" in src
        assert "status_code=503" in src


class TestRealSegmentationModelPath:
    """Opt-in: exercises the ACTUAL rembg model.

    Skipped by default because the ONNX session costs ~900MB RSS (see conftest).
    Run with:  CONFIT_VTON_DISABLE_REMBG=0 pytest backend/tests/test_vton_single_production_path.py -k RealSegmentation
    """

    pytestmark = pytest.mark.skipif(
        os.environ.get("CONFIT_VTON_DISABLE_REMBG", "1").lower() not in {"0", "false", "no"},
        reason="rembg model path disabled (set CONFIT_VTON_DISABLE_REMBG=0 to enable)",
    )

    def test_real_model_produces_person_shaped_masks(self):
        import sys
        sys.path.insert(0, (REPO / "services" / "vton-worker").as_posix())
        import numpy as np
        from PIL import Image, ImageDraw
        from pipeline.segmentation import HumanParsingEngine, AgnosticMaskGenerator

        img = Image.new("RGB", (256, 384), (235, 235, 240))
        d = ImageDraw.Draw(img)
        d.ellipse((108, 30, 148, 78), fill=(200, 170, 140))
        d.rectangle((92, 80, 164, 240), fill=(60, 80, 140))
        d.rectangle((100, 240, 156, 350), fill=(40, 40, 60))

        HumanParsingEngine._parse_cache.clear()
        res = HumanParsingEngine.parse_human_image(img)
        assert res["is_person_aware"] is True

        # Whatever engine served the request, every slot must stay semantically valid
        for slot in ("upper_inner", "upper_outer", "lower", "footwear", "accessory", "dress"):
            mask = AgnosticMaskGenerator.create_agnostic_mask(img, slot)
            assert mask.size == img.size
            checks = AgnosticMaskGenerator.validate_mask_semantics(img, mask, slot)
            assert checks["valid"], (slot, checks)
            assert 0.0 < np.asarray(mask).mean() < 255.0
        HumanParsingEngine._parse_cache.clear()
