"""Deployment dependency gate (release brief §22, regression test T3).

Production truth that motivated this file: /tryon/validate-image and
/tryon/visual-search returned 500 on Vercel with ``ModuleNotFoundError: PIL``.
Pillow was declared only in backend/requirements.txt (Docker/CI) while the
Vercel function installs the repo-root requirements.txt. The previous import
guard merged both files and therefore could not see the gap.

These tests evaluate the guard against the REAL Vercel manifest and against
that manifest with Pillow removed, so the suite fails if Pillow disappears
from what Vercel actually installs — not from some merged view.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.scripts import check_runtime_imports as guard  # noqa: E402

VERCEL_MANIFEST = ROOT / "requirements.txt"
VERCEL_MIRROR = ROOT / "api" / "requirements.txt"
DOCKER_MANIFEST = ROOT / "backend" / "requirements.txt"


def _strip(manifest_text: str, dist: str) -> str:
    """Remove every requirement line for ``dist`` (case-insensitive)."""
    return "\n".join(
        line for line in manifest_text.splitlines()
        if not re.match(rf"^\s*{re.escape(dist)}\s*([<>=!~\[]|$)", line, re.I)
    )


class TestVercelManifestIsTheOneEvaluated:
    def test_vercel_target_reads_repo_root_requirements(self):
        cfg = guard.TARGETS["vercel"]
        assert cfg["manifest"] == VERCEL_MANIFEST
        assert cfg["mirror"] == VERCEL_MIRROR
        # the serverless code that ships is backend/app + api/, never backend/tests
        assert ROOT / "backend" / "app" in cfg["code_dirs"]
        assert ROOT / "backend" / "tests" not in cfg["code_dirs"]

    def test_vercel_entrypoint_is_backend_app(self):
        src = (ROOT / "api" / "index.py").read_text()
        assert "from backend.app.main import app" in src

    def test_api_requirements_mirror_is_byte_identical(self):
        assert guard.mirror_drift("vercel") is None, guard.mirror_drift("vercel")

    def test_guard_never_merges_manifests(self):
        """The 2026-09-03 failure mode: merged view hides per-target gaps."""
        src = (ROOT / "backend" / "scripts" / "check_runtime_imports.py").read_text()
        assert "for req_file in [" not in src  # the old merging loop
        assert "missing_for_target" in src


class TestPillowIsDeclaredForVercel:
    def test_pillow_present_in_real_vercel_manifest(self):
        assert "pillow" in guard.declared_packages(VERCEL_MANIFEST)
        assert "pillow" in guard.declared_packages(VERCEL_MIRROR)

    def test_backend_app_really_imports_pil(self):
        """If this stops being true, Pillow may legitimately leave the manifest."""
        assert "PIL" in guard.imported_third_party([ROOT / "backend" / "app"])

    def test_vercel_closure_is_fully_declared(self):
        assert guard.missing_for_target("vercel") == []

    def test_docker_closure_is_fully_declared(self):
        assert guard.missing_for_target("docker") == []

    def test_T3_removing_pillow_from_vercel_manifest_fails_the_gate(self):
        hypothetical = _strip(VERCEL_MANIFEST.read_text(), "Pillow")
        assert "pillow" not in guard.parse_manifest(hypothetical)
        missing = guard.missing_for_target("vercel", manifest_text=hypothetical)
        assert any(m.startswith("PIL ") for m in missing), missing

    def test_T3_docker_manifest_cannot_cover_for_vercel(self):
        """Pillow being in backend/requirements.txt must NOT satisfy the Vercel
        target — that is precisely the merged-view bug."""
        assert "pillow" in guard.declared_packages(DOCKER_MANIFEST)
        hypothetical = _strip(VERCEL_MANIFEST.read_text(), "Pillow")
        missing = guard.missing_for_target("vercel", manifest_text=hypothetical)
        assert missing, "docker manifest leaked into the vercel evaluation"

    def test_removing_any_core_runtime_dep_fails_the_gate(self):
        for dist in ("fastapi", "sqlalchemy", "slowapi", "PyJWT"):
            hypothetical = _strip(VERCEL_MANIFEST.read_text(), dist)
            missing = guard.missing_for_target("vercel", manifest_text=hypothetical)
            assert missing, f"gate did not notice {dist} missing"


class TestOptionalListIsJustified:
    def test_every_vercel_optional_has_a_guard_note(self):
        for mod, why in guard.VERCEL_OPTIONAL.items():
            assert why and len(why) > 15, mod

    def test_pillow_is_not_optional_anywhere(self):
        assert "PIL" not in guard.VERCEL_OPTIONAL
        assert "pillow" not in {m.lower() for m in guard.VERCEL_OPTIONAL}

    def test_boto3_optional_claim_is_true_in_code(self):
        src = (ROOT / "backend" / "app" / "services" / "storage_service.py").read_text()
        assert "import boto3" in src and "except ImportError" in src

    def test_uvicorn_optional_claim_is_true_in_code(self):
        src = (ROOT / "backend" / "app" / "main.py").read_text()
        assert "import uvicorn" in src
        assert src.index('if __name__ == "__main__":') < src.index("import uvicorn")


class TestGateRunsAsCiCommand:
    def test_cli_exit_code_zero_on_current_tree(self):
        proc = subprocess.run(
            [sys.executable, "backend/scripts/check_runtime_imports.py"],
            cwd=ROOT, capture_output=True, text=True, env={"PYTHONPATH": ".", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "[vercel]" in proc.stdout and "OK" in proc.stdout

    def test_ci_workflow_invokes_the_gate(self):
        wf = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "backend/scripts/check_runtime_imports.py" in wf
