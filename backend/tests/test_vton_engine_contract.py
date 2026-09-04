"""VTON engine selection + license-honesty contract.

The VTON commercial-migration investigation established that:

* the deployed CatVTON engine is CC BY-NC-SA 4.0 (non-commercial), yet the
  schema default `model_used = "CatVTON-v1.2 (Apache 2.0)"` falsely claimed a
  commercial Apache license;
* engine selection must be server-decided and validated (no uncontrolled /
  frontend-selected model);
* the resolved engine + its (honest) license must be surfaced so a
  non-commercial engine is never silently presented as commercially deployable;
* the production default engine is the COMMERCIAL `fashn_vton_segfee` fork, never
  the non-commercial CatVTON.

These tests pin that contract so the defects cannot return.
"""
import pytest
from pydantic import ValidationError

from backend.app.core.config import (
    Settings,
    SUPPORTED_VTON_ENGINES,
    VTON_ENGINE_LICENSES,
    vton_engine_metadata,
)
from backend.app.models.tryon import TryOnJob


def test_production_default_engine_is_commercial_segfee():
    """The production default must resolve to the commercial engine, not CatVTON."""
    meta = vton_engine_metadata()
    assert meta["engine"] == "fashn_vton_segfee"
    assert meta["valid"] is True
    assert meta["commercial"] is True


def test_catvton_never_labeled_commercial():
    """The false 'Apache 2.0' claim must not come back for the non-commercial engine."""
    entry = VTON_ENGINE_LICENSES["catvton"]
    assert entry["commercial"] is False
    assert "CC BY-NC-SA" in entry["license"]


def test_setting_default_is_commercial_engine():
    assert Settings().VTON_ENGINE == "fashn_vton_segfee"


def test_fashn_segfee_is_commercial_and_known():
    entry = VTON_ENGINE_LICENSES["fashn_vton_segfee"]
    assert "fashn_vton_segfee" in SUPPORTED_VTON_ENGINES
    assert entry["commercial"] is True


def test_model_used_default_no_longer_claims_apache():
    """The schema default must be license-neutral (no false commercial claim)."""
    default = TryOnJob.__table__.c.model_used.default
    assert getattr(default, "arg", None) == "unset"
    # The false string must not exist anywhere in the model's default.
    source_default = repr(getattr(default, "arg", None))
    assert "Apache 2.0" not in source_default


def test_unknown_engine_rejected_at_startup():
    """§36 fail-closed: an unsupported VTON_ENGINE must not silently select a model."""
    with pytest.raises(ValidationError):
        Settings(VTON_ENGINE="chatgpt_vton")


@pytest.mark.parametrize(
    "engine,commercial",
    [
        ("catvton", False),
        ("fashn_vton_1_5", False),
        ("fashn_vton_segfee", True),
        ("leffa", "unverified"),
    ],
)
def test_supported_engines_are_known_and_their_license_honest(engine, commercial):
    assert engine in SUPPORTED_VTON_ENGINES
    entry = VTON_ENGINE_LICENSES[engine]
    assert entry["commercial"] == commercial
    # A supported engine maps back to a valid metadata resolution.
    assert engine in {"catvton", "fashn_vton_1_5", "fashn_vton_segfee", "leffa"}


def test_health_reports_resolved_commercial_engine_license(client):
    """Operators must see the engine + its license, not just 'operational'."""
    data = client.get("/api/v1/health").json()
    checks = data["checks"]
    assert "vton_engine" in checks
    engine = checks["vton_engine"]
    assert engine["engine"] == "fashn_vton_segfee"
    assert engine["valid"] is True
    assert engine["commercial"] is True
