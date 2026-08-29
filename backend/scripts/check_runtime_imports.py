"""Deployment safety net: every third-party package imported by the backend
must be declared in requirements.txt — otherwise Vercel builds succeed but the
function dies at import with FUNCTION_INVOCATION_FAILED (the 2026-08-29
outage: slowapi was imported but never declared).

Run:  PYTHONPATH=. python3 backend/scripts/check_runtime_imports.py
Exit 0 = all runtime imports declared. Exit 1 = missing declarations.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# import-name -> pip package name for the known mismatches
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
}

STDLIB = set(sys.stdlib_module_names)


def declared_packages() -> set[str]:
    pkgs = set()
    for req_file in [ROOT / "requirements.txt", ROOT / "backend" / "requirements.txt"]:
        if not req_file.exists():
            continue
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.split("[")[0].split(">=")[0].split("==")[0].split("<")[0].strip()
            if name:
                pkgs.add(name.lower().replace("_", "-"))
    return pkgs


def imported_third_party() -> set[str]:
    mods = set()
    for py in (ROOT / "backend" / "app").rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods.add(node.module.split(".")[0])
    # drop stdlib and our own package
    return {m for m in mods if m not in STDLIB and m != "backend"}


def main() -> int:
    declared = declared_packages()
    missing = []
    for mod in sorted(imported_third_party()):
        pkg = IMPORT_TO_PACKAGE.get(mod, mod).lower().replace("_", "-")
        if pkg not in declared:
            missing.append(f"{mod} (package: {pkg})")
    if missing:
        print("MISSING from requirements.txt — would crash the deployment at import:")
        for m in missing:
            print(f"  ✗ {m}")
        return 1
    print("OK: every third-party runtime import is declared in requirements.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
