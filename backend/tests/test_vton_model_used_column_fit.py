"""Regression (production incident 2026-09-05): the worker reports a
66-character model string; tryon_jobs.model_used is VARCHAR(50). The old
code truncated to 100, so the completion commit failed with Postgres 22001
(value too long) and a SUCCESSFUL GPU render 500'd on the way back.

These tests pin the invariant: whatever string is written to
job.model_used must fit the actual column width, and the clamp constant
must track the model definition (so widening one without the other fails
CI).
"""

from backend.app.models.tryon import TryOnJob
from backend.app.services.tryon_service import _MODEL_USED_COLUMN_WIDTH, _clamp_model_used

# The exact string the production segfee worker returned on 2026-09-05:
PROD_WORKER_MODEL_STRING = (
    "fashn-vton-v1.5 (fashn_vton_segfee, segmentation-free; fork 7c0f10af)"
)


def test_production_worker_string_clamped_to_column_width():
    assert len(PROD_WORKER_MODEL_STRING) > _MODEL_USED_COLUMN_WIDTH  # guards the fixture
    clamped = _clamp_model_used(PROD_WORKER_MODEL_STRING)
    assert len(clamped) <= _MODEL_USED_COLUMN_WIDTH
    assert clamped.startswith("fashn-vton-v1.5")


def test_clamp_helper_bounds():
    assert _clamp_model_used("") == ""
    assert _clamp_model_used("short") == "short"
    assert len(_clamp_model_used("x" * 500)) == _MODEL_USED_COLUMN_WIDTH
    assert _clamp_model_used(None) == "None"


def test_clamp_constant_matches_model_column():
    """The clamp must track the real schema definition."""
    col = TryOnJob.__table__.c["model_used"]
    assert col.type.length == _MODEL_USED_COLUMN_WIDTH


def test_clamped_value_writes_to_db():
    from backend.tests.conftest import TestingSessionLocal
    from backend.app.models.tryon import TryOnJob as J

    with TestingSessionLocal() as db:
        j = J(
            job_id="fit_test_%d" % 1,
            user_id=None,
            input_person_image_url="https://example.com/p.png",
            model_used=_clamp_model_used(PROD_WORKER_MODEL_STRING),
        )
        db.add(j)
        db.commit()
        db.refresh(j)
        assert len(j.model_used) <= _MODEL_USED_COLUMN_WIDTH
        db.delete(j)
        db.commit()
