"""Deployment dependency gate — models EACH deployment target separately.

History of this guard:
  * 2026-08-29: slowapi was imported but never declared -> every Vercel
    invocation died with FUNCTION_INVOCATION_FAILED.
  * 2026-09-03: Pillow was declared ONLY in backend/requirements.txt (the
    Docker/CI file) while the Vercel function installs requirements.txt at the
    repo root. The previous version of this script MERGED both files, so it
    reported "OK" while production /tryon/validate-image and
    /tryon/visual-search crashed with ModuleNotFoundError: PIL.

The lesson: a merged requirements view proves nothing about a deployment
target. This script therefore evaluates the import closure of the code that
ships to each target against the manifest that target actually installs.

Targets
-------
  vercel   code:  backend/app  (+ api/index.py)
           pins:  requirements.txt  (== api/requirements.txt, byte-identical)
           optional: packages that are imported lazily inside an explicit
                     ImportError guard AND whose feature is disabled by
                     configuration in the serverless deployment (see
                     VERCEL_OPTIONAL below — each entry is justified).
  docker   code:  backend/app + backend/tests
           pins:  backend/requirements.txt

Run:  PYTHONPATH=. python3 backend/scripts/check_runtime_imports.py
Exit 0 = every target's import closure is declared. Exit 1 = a gap exists.

Importable API (used by tests/test_deployment_dependency_manifest.py):
  declared_packages(manifest_path) -> set[str]
  imported_third_party(code_dirs) -> set[str]
  missing_for_target(target, *, manifest_text=None) -> list[str]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]

# import-name -> pip distribution name for the known mismatches
IMPORT_TO_PACKAGE = {
    "PIL": "pillow",
    "jwt": "pyjwt",
    "jose": "python-jose",
    "yaml": "pyyaml",
    "cv2": "opencv-python-headless",
    "sklearn": "scikit-learn",
    "slowapi": "slowapi",
    "pydantic_settings": "pydantic-settings",
    "email_validator": "email-validator",
    "dotenv": "python-dotenv",
    "multipart": "python-multipart",
    "google": "google-generativeai",
}

STDLIB = set(sys.stdlib_module_names)

# Local packages that are not third-party (vton-worker etc.) and not deployed with backend
LOCAL_PACKAGES = {"pipeline", "services", "worker", "modal_app", "backend", "api",
                  # CONFIT's VTON engine adapter package (services/vton-worker/engine).
                  # A local package, not a third-party dependency: the Docker image
                  # ships it as repo source, so it must NOT be declared as a pip pin.
                  "engine"}

# Packages the Vercel function may legitimately lack. EVERY entry must name
# the guard that makes the absence safe; an unguarded lazy import is NOT
# optional (that is exactly how the Pillow outage happened).
VERCEL_OPTIONAL = {
    # celery is imported by backend/app/workers/*; wardrobe_service enqueues
    # inside try/except and falls back to inline analysis when the broker or
    # the package is unavailable. Vercel runs no Celery worker.
    "celery": "workers/ package; wardrobe_service guards enqueue failure and runs inline",
    # test-only tooling that lives in backend/tests, never in backend/app
    "pytest": "test suite only (backend/tests, never imported by backend/app)",
    "pytest_asyncio": "test suite only (backend/tests, never imported by backend/app)",
    "numpy": "test suite only (vton mask tests); backend/app has no numpy import",
    # alembic is an operator CLI step (see docs/CONFIT_Production_Run_and_Environment_Guide.md);
    # backend/app imports it only inside the schema-drift gate under try/except.
    "alembic": "operator CLI; runtime gate imports under ImportError guard",
    # main.py imports uvicorn only under `if __name__ == "__main__"` (local dev
    # server); Vercel imports the module, it never executes that block.
    "uvicorn": "main.py __main__ block only; Vercel/mangum never runs it",
}

TARGETS = {
    "vercel": {
        "code_dirs": [ROOT / "backend" / "app", ROOT / "api"],
        "manifest": ROOT / "requirements.txt",
        "mirror": ROOT / "api" / "requirements.txt",
        "optional": set(VERCEL_OPTIONAL),
    },
    "docker": {
        "code_dirs": [ROOT / "backend" / "app", ROOT / "backend" / "tests"],
        "manifest": ROOT / "backend" / "requirements.txt",
        "mirror": None,
        "optional": set(),
    },
}


def _normalise(name: str) -> str:
    return name.lower().replace("_", "-")


def parse_manifest(text: str) -> set[str]:
    pkgs: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = line.split("[")[0]
        for sep in (">=", "==", "<=", "~=", "!=", ">", "<", ";", " "):
            name = name.split(sep)[0]
        name = name.strip()
        if name:
            pkgs.add(_normalise(name))
    return pkgs


def declared_packages(manifest_path: Path) -> set[str]:
    if not manifest_path.exists():
        return set()
    return parse_manifest(manifest_path.read_text())


def imported_third_party(code_dirs: Iterable[Path]) -> set[str]:
    """Top-level third-party modules imported ANYWHERE in the given code —
    including lazy imports inside functions, which is where the outages hid."""
    mods: set[str] = set()
    for base_dir in code_dirs:
        if not base_dir.exists():
            continue
        files = [base_dir] if base_dir.is_file() else base_dir.rglob("*.py")
        for py in files:
            if "__pycache__" in str(py):
                continue
            try:
                tree = ast.parse(py.read_text(), filename=str(py))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        mods.add(a.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods.add(node.module.split(".")[0])
    return {m for m in mods if m not in STDLIB and m not in LOCAL_PACKAGES}


def missing_for_target(target: str, *, manifest_text: Optional[str] = None) -> list[str]:
    """Return human-readable gaps for one deployment target.

    ``manifest_text`` lets tests evaluate a hypothetical manifest (e.g. the
    real one with Pillow removed) without touching the repository files.
    """
    cfg = TARGETS[target]
    declared = parse_manifest(manifest_text) if manifest_text is not None else declared_packages(cfg["manifest"])
    missing: list[str] = []
    for mod in sorted(imported_third_party(cfg["code_dirs"])):
        pkg = _normalise(IMPORT_TO_PACKAGE.get(mod, mod))
        if pkg in declared:
            continue
        if _normalise(mod) in {_normalise(o) for o in cfg["optional"]}:
            continue
        missing.append(f"{mod} (package: {pkg})")
    return missing


def mirror_drift(target: str) -> Optional[str]:
    cfg = TARGETS[target]
    mirror = cfg.get("mirror")
    if not mirror:
        return None
    if not mirror.exists():
        return f"{mirror.relative_to(ROOT)} is missing"
    if mirror.read_bytes() != cfg["manifest"].read_bytes():
        return f"{mirror.relative_to(ROOT)} is not byte-identical to {cfg['manifest'].relative_to(ROOT)}"
    return None


def main() -> int:
    rc = 0
    for target, cfg in TARGETS.items():
        missing = missing_for_target(target)
        drift = mirror_drift(target)
        label = f"[{target}] manifest={cfg['manifest'].relative_to(ROOT)}"
        if missing or drift:
            rc = 1
            print(f"{label}: FAIL")
            for m in missing:
                print(f"  ✗ undeclared runtime import: {m}")
            if drift:
                print(f"  ✗ {drift}")
        else:
            print(f"{label}: OK — import closure fully declared")
    if rc:
        print("\nAn undeclared import kills the deployment at first use "
              "(FUNCTION_INVOCATION_FAILED / ModuleNotFoundError). Fix the manifest, "
              "not this script.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
