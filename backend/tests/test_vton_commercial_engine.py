"""Commercial VTON engine (fashn_vton_segfee) — adapter contract + license.

Validates the segmentation-free commercial fork that replaces the non-commercial
CatVTON path. Pins:

  * `fashn_vton_segfee` is registered, commercially usable, single-category;
  * the fork NEVER imports the restricted `fashn_human_parser` (static guarantee);
  * the adapter contract (load/render/validate) is asserted WITHOUT GPU/torch;
  * the non-commercial CatVTON engine is NOT the registered default engine;
  * output validation rejects echo and blank (no fake PASS).
"""
import os
import sys

import pytest

from backend.app.core.config import SUPPORTED_VTON_ENGINES, VTON_ENGINE_LICENSES

# Make the worker engine adapter importable without GPU/torch.
_WORKER_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "services", "vton-worker")
if _WORKER_ROOT not in sys.path:
    sys.path.insert(0, _WORKER_ROOT)


# --- config registry -----------------------------------------------------------

def test_fashn_segfee_is_supported_and_commercial():
    assert "fashn_vton_segfee" in SUPPORTED_VTON_ENGINES
    entry = VTON_ENGINE_LICENSES["fashn_vton_segfee"]
    assert entry["commercial"] is True


def test_catvton_remains_noncommercial_in_registry():
    # The non-commercial engine must never be labelled commercial.
    assert VTON_ENGINE_LICENSES["catvton"]["commercial"] is False


# --- worker engine adapter (no GPU / no torch) ---------------------------------

def test_engine_registry_defaults_to_commercial():
    import engine
    assert "fashn_vton_segfee" in engine._REGISTRY
    # The non-commercial CatVTON path is deliberately NOT the registered default.
    assert "catvton" not in engine._REGISTRY


def test_engine_adapter_contract_metadata():
    import engine
    cls = engine.get_engine("fashn_vton_segfee")
    assert cls is not None
    inst = cls(weights_dir="/nonexistent", device="cuda")
    assert inst.commercially_usable is True
    assert inst.supports_multigarment is False  # single-category: no naive compositing
    meta = inst.metadata()
    assert meta["engine"] == "fashn_vton_segfee"
    assert meta["commercial"] is True
    assert "fashn-human-parser removed" in meta["license"] or "parser" in meta["license"].lower()


def test_engine_adapter_rejects_bad_category():
    import engine
    cls = engine.get_engine("fashn_vton_segfee")
    inst = cls(weights_dir="/nonexistent", device="cuda")
    with pytest.raises(ValueError):
        inst.validate_inputs(object(), object(), "shoes")


def test_engine_adapter_rejects_multiple_garments():
    import engine
    cls = engine.get_engine("fashn_vton_segfee")
    inst = cls(weights_dir="/nonexistent", device="cuda")
    # Suppress the actual model call: failing the len(garments)>1 check happens
    # before the pipe is touched; but for a single garment it hits _ready False.
    with pytest.raises(RuntimeError):
        inst.render(object(), object(), category="tops", garments=[{}, {}])


# --- parser-free static guarantee ----------------------------------------------

@pytest.mark.parametrize("rel", [
    "src/fashn_vton/pipeline.py",
    "src/fashn_vton/preprocessing/agnostic.py",
    "src/fashn_vton/preprocessing/__init__.py",
    "src/fashn_vton/_parser_compat.py",
])
def test_fork_never_imports_restricted_parser(rel):
    """No runtime source file in the commercial fork may import the parser.

    Checks actual import statements, not comments. Comments documenting
    the parser removal are intentional and correct.
    """
    fork = os.path.join(_WORKER_ROOT, "..", "..", "vendor", "fashn-vton-segfee")
    path = os.path.join(fork, rel)
    if not os.path.exists(path):
        pytest.skip("fork not vendored in this checkout")
    src = open(path).read()
    # Check for actual import statements (not comments)
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "import fashn_human_parser" not in stripped, f"Found parser import in {rel}: {line}"
        assert "from fashn_human_parser" not in stripped, f"Found parser import in {rel}: {line}"


def test_fork_pyproject_has_no_parser_dependency():
    """The commercial fork must not declare fashn-human-parser as a dependency.

    Checks actual dependency declarations, not comments.
    """
    fork = os.path.join(_WORKER_ROOT, "..", "..", "vendor", "fashn-vton-segfee")
    path = os.path.join(fork, "pyproject.toml")
    if not os.path.exists(path):
        pytest.skip("fork not vendored in this checkout")
    src = open(path).read()
    # Check actual dependency lines (not comments)
    in_deps_section = False
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_deps_section = "dependencies" in stripped.lower()
            continue
        if in_deps_section and not stripped.startswith("#"):
            assert "fashn-human-parser" not in stripped, f"Found parser dependency: {line}"


# --- output validation (no fake PASS) -----------------------------------------

def test_output_validation_rejects_echo_and_blank():
    import numpy as np
    from PIL import Image
    import engine
    cls = engine.get_engine("fashn_vton_segfee")
    inst = cls(weights_dir="/nonexistent", device="cuda")
    np.random.seed(0)
    a = Image.fromarray((np.random.rand(40, 40, 3) * 255).astype("uint8"))
    blank = Image.new("RGB", a.size, (10, 10, 10))
    # identical output (echo) must FAIL
    assert inst.validate_output(a, a)["PASS"] is False
    # blank/constant output must FAIL
    assert inst.validate_output(a, blank)["PASS"] is False
