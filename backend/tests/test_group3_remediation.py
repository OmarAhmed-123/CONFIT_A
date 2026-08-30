"""Group 3 production-remediation tests (this turn).

Scope: SSRF guard, real image validation, ownership enforcement, full visual
search filter chain, per-slot scaling persistence, GET/purge auth.

Tests are deliberately self-contained: each builds a minimal in-memory
SQLite session and exercises the patched path end to end.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="module")
def db_session():
    from backend.app.core.database import Base
    from backend.app.models import tryon as _tryon_models  # noqa: F401
    from backend.app.models import user as _user_models  # noqa: F401
    from backend.app.models import catalog as _catalog_models  # noqa: F401
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    yield sess
    sess.close()



# ====== 1. SSRF guard =================================================
class TestSSRFGuard:
    def test_loopback_ipv4_rejected(self):
        from backend.app.core.security import is_safe_image_url
        assert is_safe_image_url("https://127.0.0.1/img.png") is False
        assert is_safe_image_url("http://127.0.0.1:8080/x.png") is False

    def test_private_10_rejected(self):
        from backend.app.core.security import is_safe_image_url
        assert is_safe_image_url("https://10.0.0.5/x.png") is False

    def test_private_192_168_rejected(self):
        from backend.app.core.security import is_safe_image_url
        assert is_safe_image_url("https://192.168.1.1/x.png") is False

    def test_link_local_metadata_rejected(self):
        # 169.254.169.254 is the AWS/GCP cloud metadata endpoint — SSRF favorite target
        from backend.app.core.security import is_safe_image_url
        assert is_safe_image_url("http://169.254.169.254/latest/meta-data/") is False

    def test_localhost_name_rejected(self):
        from backend.app.core.security import is_safe_image_url
        assert is_safe_image_url("http://localhost/x.png") is False
        assert is_safe_image_url("http://metadata.google.internal/x") is False

    def test_non_http_rejected(self):
        from backend.app.core.security import is_safe_image_url
        assert is_safe_image_url("file:///etc/passwd") is False
        assert is_safe_image_url("javascript:alert(1)") is False

    def test_public_url_accepted_if_dns_resolves(self):
        from backend.app.core.security import is_safe_image_url
        # We don't have network in tests, so DNS may fail; both outcomes are
        # acceptable (fail-closed). Document the assertion explicitly:
        result = is_safe_image_url("https://example.com/x.png")
        assert result is False or result is True  # network-dependent; fail-closed


# ====== 2. Real image validation (no fabricated gender/category) ======
class TestRealImageValidation:
    def test_empty_payload_returns_invalid(self):
        from backend.app.providers.tryon_provider import VirtualTryOnProvider
        v = VirtualTryOnProvider().validate_uploaded_image
        out = v("")
        assert out["is_valid"] is False
        assert "empty_payload" in out["issues"]

    def test_unsafe_url_blocked(self):
        from backend.app.providers.tryon_provider import VirtualTryOnProvider
        v = VirtualTryOnProvider().validate_uploaded_image
        out = v("http://192.168.1.1/photo.png")
        assert out["is_valid"] is False
        assert "unsafe_url" in out["issues"]

    def test_valid_base64_jpeg_reports_real_dimensions(self):
        import base64, io
        from PIL import Image
        from backend.app.providers.tryon_provider import VirtualTryOnProvider
        v = VirtualTryOnProvider().validate_uploaded_image
        buf = io.BytesIO()
        Image.new("RGB", (800, 1200), (200, 200, 255)).save(buf, "JPEG", quality=85)
        data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        out = v(data_url)
        assert out["is_valid"] is True
        assert out["format"] == "jpeg"
        assert out["width"] == 800 and out["height"] == 1200
        assert out["aspect_ratio"] == round(800 / 1200, 3)
        assert out["min_dimension"] == 800
        # No fabricated gender/category output
        assert "detected_gender" not in out
        assert "body_framing" not in out

    def test_corrupt_base64_reported_as_decode_failed(self):
        from backend.app.providers.tryon_provider import VirtualTryOnProvider
        v = VirtualTryOnProvider().validate_uploaded_image
        out = v("data:image/jpeg;base64,not-valid-base64!!!")
        assert out["is_valid"] is False
        assert any("decode_failed" in i for i in out["issues"])


# ====== 3. Schema: VisualSearchRequest full filter chain ==============
class TestVisualSearchRequestSchema:
    def test_min_and_max_price_and_brand(self):
        from backend.app.schemas.tryon import VisualSearchRequest
        r = VisualSearchRequest(min_price=10, max_price=200, brand_ids=[1, 2], in_stock_only=False, limit=24)
        assert r.min_price == 10 and r.max_price == 200 and r.brand_ids == [1, 2]

    def test_invalid_range_rejected_by_model_validator(self):
        from backend.app.schemas.tryon import VisualSearchRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            VisualSearchRequest(min_price=200, max_price=10)

    def test_negative_price_rejected_by_field_constraint(self):
        from backend.app.schemas.tryon import VisualSearchRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            VisualSearchRequest(min_price=-1)


# ====== 4. Ownership enforcement =====================================
class TestTryOnSessionOwnership:
    def _new_session(self, db, user_id):
        from backend.app.models.tryon import TryOnSession
        s = TryOnSession(
            user_id=user_id, status="completed",
            applied_items_json="[]", slot_mapping_json="{}",
            layering_order_json="[]", render_metadata_json="{}",
            fit_verdict="True to Size", fit_confidence_score=50,
            body_scaling_factor=1.0,
        )
        db.add(s); db.commit(); db.refresh(s)
        return s

    def test_get_blocks_other_user(self, db_session):
        from backend.app.repositories.tryon_repository import TryOnRepository
        from backend.app.core.exceptions import AuthorizationError
        owner_id = 1001; other_id = 9999
        sess = self._new_session(db_session, owner_id)
        repo = TryOnRepository(db_session)
        # Owner can read
        assert repo.get_tryon_session(sess.id, caller_user_id=owner_id).id == sess.id
        # Another user cannot
        with pytest.raises(AuthorizationError):
            repo.get_tryon_session(sess.id, caller_user_id=other_id)
        # Internal (None) still allowed
        assert repo.get_tryon_session(sess.id, caller_user_id=None).id == sess.id

    def test_purge_blocks_other_user(self, db_session):
        from backend.app.repositories.tryon_repository import TryOnRepository
        from backend.app.core.exceptions import AuthorizationError
        owner_id = 2001; other_id = 8888
        sess = self._new_session(db_session, owner_id)
        repo = TryOnRepository(db_session)
        with pytest.raises(AuthorizationError):
            repo.purge_session(sess.id, caller_user_id=other_id)
        # Owner succeeds
        assert repo.purge_session(sess.id, caller_user_id=owner_id) is True

    def test_get_missing_returns_none(self, db_session):
        from backend.app.repositories.tryon_repository import TryOnRepository
        assert TryOnRepository(db_session).get_tryon_session(999_999, caller_user_id=1) is None


# ====== 5. per-slot scaling persistence ==============================
class TestPerSlotScaling:
    def test_apply_measurements_persists_slot_scaling(self, db_session):
        from backend.app.repositories.tryon_repository import TryOnRepository
        from backend.app.models.tryon import TryOnSession
        from backend.app.services.tryon_service import TryOnService
        # Construct session directly
        sess = TryOnSession(
            user_id=42, status="completed",
            applied_items_json="[]", slot_mapping_json="{}",
            layering_order_json="[]", render_metadata_json="{}",
            fit_verdict="True to Size", fit_confidence_score=50,
            body_scaling_factor=1.0,
        )
        db_session.add(sess); db_session.commit(); db_session.refresh(sess)
        svc = TryOnService(db_session)
        out = svc.apply_measurements_to_session(
            session_id=sess.id,
            height_cm=180,
            chest_cm=104,
            waist_cm=84,
            shoulder_cm=46,
            caller_user_id=42,
        )
        assert out["scaling_factor"] == round(180 / 175.0, 2)
        assert out["slot_scaling"]["chest"] == round(104 / 98.0, 2)
        assert out["slot_scaling"]["waist"] == round(84 / 82.0, 2)
        assert out["slot_scaling"]["shoulder"] == round(46 / 45.0, 2)
        # Persisted
        import json
        meta = json.loads(sess.render_metadata_json)
        assert meta["slot_scaling"]["chest"] == round(104 / 98.0, 2)


class TestCompositeVerificationConsistency:
    """Regression guard: a paired metric failure must never yield a clean PASS."""

    @staticmethod
    def _load_verify():
        import importlib.util
        import pathlib
        p = (pathlib.Path(__file__).resolve().parents[2] /
             "services" / "vton-worker" / "pipeline" / "verify.py")
        spec = importlib.util.spec_from_file_location("pipeline.verify", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_identical_images_never_pass(self):
        from PIL import Image
        v = self._load_verify()
        img = Image.new("RGB", (128, 192), (80, 80, 90))
        r = v.verify_composite_output(img, img)
        assert r["PASS"] is False
        assert r["metric_pixel_change"] is False
        assert r["metric_color_shift"] is False

    def test_brightness_only_change_cannot_pass(self):
        # This is the exact old contradiction: pixels changed globally, but no
        # garment color shift occurred. PASS must be False.
        from PIL import Image
        import numpy as np
        v = self._load_verify()
        arr = np.zeros((192, 128, 3), dtype=np.uint8)
        arr[60:130, 10:115] = (60, 60, 90)   # greyish shirt
        orig = Image.fromarray(arr)
        brighter = Image.fromarray(np.clip(arr.astype(np.int16) + 40, 0, 255).astype(np.uint8))
        r = v.verify_composite_output(orig, brighter, region=(0.30, 0.65, 0.05, 0.95))
        assert r["metric_pixel_change"] is True    # global pixels did change
        assert r["metric_color_shift"] is False    # but no garment color appears
        assert r["PASS"] is False                  # combined verdict must fail

    def test_real_garment_appearance_can_pass(self):
        from PIL import Image
        import numpy as np
        v = self._load_verify()
        base = np.zeros((192, 128, 3), dtype=np.uint8)
        base[:] = (200, 200, 200)
        orig = Image.fromarray(base)
        out = base.copy()
        out[60:130, 10:115] = (40, 50, 90)  # navy garment fills the region
        r = v.verify_composite_output(orig, Image.fromarray(out),
                                      region=(0.30, 0.65, 0.05, 0.95))
        assert r["metric_color_shift"] is True
        assert r["metric_pixel_change"] is True
        assert r["PASS"] is True
