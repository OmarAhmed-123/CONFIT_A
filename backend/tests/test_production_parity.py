"""Local -> production parity: the deployment contract as executable checks.

Production for this product is GitHub main -> Vercel (Python serverless
function ``api/index.py`` importing ``backend.app.main:app``) -> Neon
PostgreSQL -> Modal GPU worker. These tests fail when the repository drifts
away from what that path actually needs. They do not need a database.

Covered:
  * Settings production contract: refuses sqlite, publicly-known / short
    secrets, unknown ENVIRONMENT; accepts a proper production config.
  * Upload features answer 501 FEATURE_NOT_CONFIGURED in production without
    object storage (never a filesystem PermissionError 500).
  * Vercel manifest == api/ mirror; vercel.json routes /api/* to the function
    that imports the canonical app; frontend calls the same-origin ``/api/v1``.
  * GPU worker URL derivation incl. explicit overrides (Modal hash-truncated
    readiness label).
  * The only localhost defaults left in the backend are the documented dev
    conveniences (CORS origins, REDIS_URL) — nothing else may point at a
    developer machine.
  * The deployment contract document exists and mentions every environment
    variable the production validator enforces.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]

GOOD_PROD_ENV = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql://u:p@db.example.neon.tech/confit?sslmode=require",
    "SECRET_KEY": "x" * 48,
    "JWT_REFRESH_SECRET": "y" * 48,
    "ENCRYPTION_KEY_FOR_BODY_DATA": "z" * 48,
}


def _settings(**overrides):
    """Build a Settings instance from an explicit environment (no .env files)."""
    from backend.app.core.config import Settings

    env = {**GOOD_PROD_ENV, **overrides}
    return Settings(_env_file=None, **env)


class TestProductionSettingsContract:
    def test_valid_production_configuration_boots(self):
        s = _settings()
        assert s.is_production is True

    def test_sqlite_refused_in_production(self):
        with pytest.raises(ValidationError, match="PostgreSQL"):
            _settings(DATABASE_URL="sqlite:///./backend/data/confit.db")

    @pytest.mark.parametrize("field", ["SECRET_KEY", "JWT_REFRESH_SECRET", "ENCRYPTION_KEY_FOR_BODY_DATA"])
    def test_publicly_known_values_refused(self, field):
        from backend.app.core.config import PUBLICLY_KNOWN_SECRET_VALUES

        for known in PUBLICLY_KNOWN_SECRET_VALUES:
            with pytest.raises(ValidationError, match="publicly known"):
                _settings(**{field: known})

    @pytest.mark.parametrize("field", ["SECRET_KEY", "JWT_REFRESH_SECRET", "ENCRYPTION_KEY_FOR_BODY_DATA"])
    def test_short_secret_refused(self, field):
        with pytest.raises(ValidationError, match="shorter than"):
            _settings(**{field: "short"})

    def test_published_compose_and_docs_values_are_in_the_blocklist(self):
        """The two values that were committed to docker-compose.yml / docs in
        this repository's history must be refused forever."""
        from backend.app.core.config import PUBLICLY_KNOWN_SECRET_VALUES as KNOWN

        assert "confit_super_secret_jwt_encryption_key_2026_production_grade" in KNOWN
        assert "confit_body_privacy_encryption_secret_key_32bytes!" in KNOWN
        assert "confit_production_jwt_secret_key_2026_secure" in KNOWN
        assert "confit_jwt_signing_key_production_2026_secure_key" in KNOWN

    def test_unknown_environment_refused_everywhere(self):
        with pytest.raises(ValidationError, match="ENVIRONMENT"):
            _settings(ENVIRONMENT="prod")
        with pytest.raises(ValidationError, match="ENVIRONMENT"):
            _settings(ENVIRONMENT="Production-EU")

    def test_development_keeps_defaults_only_because_environment_says_so(self):
        from backend.app.core.config import Settings

        s = Settings(_env_file=None, ENVIRONMENT="development")
        assert s.is_production is False
        assert s.DATABASE_URL.startswith("sqlite")

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ('["https://confit-a.vercel.app","https://confit.vercel.app"]',
             ["https://confit-a.vercel.app", "https://confit.vercel.app"]),
            ("https://confit-a.vercel.app, https://confit.vercel.app/",
             ["https://confit-a.vercel.app", "https://confit.vercel.app"]),
            ("https://confit-a.vercel.app", ["https://confit-a.vercel.app"]),
        ],
        ids=["json-list", "csv", "single"],
    )
    def test_cors_origins_accepts_the_string_forms_hosting_providers_inject(self, monkeypatch, raw, expected):
        """Vercel/Modal/docker inject CORS_ORIGINS as a plain string. Until this
        validator existed, a comma-separated or single-origin value crashed
        Settings() at import time (SettingsError) -> every serverless request
        failed. The value must be read from the real environment source, not
        passed as a constructor kwarg, to exercise the env-decoding path."""
        from backend.app.core.config import Settings

        for k, v in GOOD_PROD_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("CORS_ORIGINS", raw)
        assert Settings(_env_file=None).CORS_ORIGINS == expected

    def test_cors_origin_without_scheme_is_refused(self):
        with pytest.raises(ValidationError, match="http"):
            _settings(CORS_ORIGINS="confit-a.vercel.app")

    def test_local_storage_does_not_block_boot_but_is_not_production_grade(self):
        s = _settings(STORAGE_PROVIDER="local")
        assert s.STORAGE_PROVIDER == "local"
        from backend.app.services import storage_service

        assert storage_service.storage_status.__doc__  # config-only view exists
        # the guard decides at call time from the live settings (tested below)


class TestUploadsFailClosedInProductionWithoutObjectStorage:
    def test_require_production_storage_raises_501_feature_not_configured(self, monkeypatch):
        from backend.app.core.config import settings
        from backend.app.core.exceptions import FeatureNotConfiguredError
        from backend.app.services import storage_service

        monkeypatch.setattr(settings, "ENVIRONMENT", "production", raising=False)
        monkeypatch.setattr(settings, "STORAGE_PROVIDER", "local", raising=False)
        with pytest.raises(FeatureNotConfiguredError) as ei:
            storage_service.require_production_storage("wardrobe_upload")
        assert ei.value.status_code == 501

    def test_health_reports_storage_honestly(self, monkeypatch):
        from backend.app.core.config import settings
        from backend.app.services.storage_service import storage_status

        monkeypatch.setattr(settings, "STORAGE_PROVIDER", "local", raising=False)
        st = storage_status()
        assert st["provider"] == "local"
        assert st["production_grade"] is False

    def test_upload_call_sites_use_the_guard_not_a_silent_fallback(self):
        wardrobe = (REPO / "backend/app/services/wardrobe_service.py").read_text()
        moodboard = (REPO / "backend/app/controllers/moodboard_controller.py").read_text()
        assert "require_production_storage(" in wardrobe
        assert "require_production_storage(" in moodboard
        # the old pattern: on storage failure, write to ./uploads and carry on
        assert "except Exception" not in wardrobe.split("def _store_image")[1].split("def ")[0]


class TestVercelDeploymentArtifacts:
    def test_vercel_manifest_mirror_is_identical(self):
        root = (REPO / "requirements.txt").read_text()
        api = (REPO / "api/requirements.txt").read_text()
        assert root == api, "api/requirements.txt must be byte-identical to requirements.txt"

    def test_vercel_json_routes_api_to_the_python_function(self):
        cfg = json.loads((REPO / "vercel.json").read_text())
        assert "api/index.py" in cfg["functions"]
        rewrites = {r["source"]: r["destination"] for r in cfg["rewrites"]}
        assert rewrites.get("/api/:path*") == "/api/index"
        assert cfg["functions"]["api/index.py"]["maxDuration"] >= 30

    def test_entrypoint_imports_the_canonical_app(self):
        src = (REPO / "api/index.py").read_text()
        tree = ast.parse(src)
        imported = [
            (n.module, [a.name for a in n.names]) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        ]
        assert ("backend.app.main", ["app"]) in imported
        assert not (REPO / "api/backend").exists(), "vendored backend copy must not come back"

    def test_manifest_contains_every_production_runtime_driver(self):
        req = (REPO / "requirements.txt").read_text().lower()
        for pkg in ("pg8000", "mangum", "pillow", "fastapi", "sqlalchemy", "httpx", "pydantic-settings"):
            assert pkg in req, f"{pkg} missing from the Vercel manifest"

    def test_frontend_calls_same_origin_api(self):
        src = (REPO / "frontend/src/services/apiClient.ts").read_text()
        assert "'/api/v1'" in src or '"/api/v1"' in src
        assert "localhost" not in src

    def test_dev_quick_login_is_compiled_out_of_production(self):
        src = (REPO / "frontend/src/views/auth/AuthModal.tsx").read_text()
        assert "import.meta.env.DEV" in src


class TestWorkerUrlDerivation:
    @pytest.fixture
    def derive(self):
        from backend.app.services.tryon_service import TryOnService

        svc = TryOnService.__new__(TryOnService)
        return lambda url: TryOnService._derive_worker_urls(svc, url)

    def test_modal_layout_derives_health_only_and_falls_back_readiness(self, derive, monkeypatch):
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "VTON_WORKER_HEALTH_URL", None, raising=False)
        monkeypatch.setattr(settings, "VTON_WORKER_READINESS_URL", None, raising=False)
        monkeypatch.delenv("VTON_WORKER_HEALTH_URL", raising=False)
        monkeypatch.delenv("VTON_WORKER_READINESS_URL", raising=False)
        p = "https://acct--confit-vton-worker-vtoninferenceservice-process.modal.run"
        health, readiness, process = derive(p)
        assert process == p
        assert health == p.replace("-process", "-health")
        assert readiness == health, "hash-truncated readiness label is NOT derivable"
        assert "-readiness.modal.run" not in readiness

    def test_explicit_readiness_override_wins(self, derive, monkeypatch):
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "VTON_WORKER_HEALTH_URL", None, raising=False)
        monkeypatch.setattr(settings, "VTON_WORKER_READINESS_URL",
                            "https://acct--confit-vton-worker-vtoninferenceservice-r-f73a19.modal.run", raising=False)
        p = "https://acct--confit-vton-worker-vtoninferenceservice-process.modal.run"
        _, readiness, _ = derive(p)
        assert readiness.endswith("-r-f73a19.modal.run")

    def test_fastapi_single_host_layouts(self, derive, monkeypatch):
        from backend.app.core.config import settings

        monkeypatch.setattr(settings, "VTON_WORKER_HEALTH_URL", None, raising=False)
        monkeypatch.setattr(settings, "VTON_WORKER_READINESS_URL", None, raising=False)
        monkeypatch.delenv("VTON_WORKER_HEALTH_URL", raising=False)
        monkeypatch.delenv("VTON_WORKER_READINESS_URL", raising=False)
        h, r, p = derive("https://gpu.example.com/process")
        assert (h, r, p) == ("https://gpu.example.com/health", "https://gpu.example.com/readiness",
                             "https://gpu.example.com/process")
        h, r, p = derive("https://gpu.example.com")
        assert (h, r, p) == ("https://gpu.example.com/health", "https://gpu.example.com/readiness",
                             "https://gpu.example.com/process")


class TestNoDeveloperMachineReferencesReachProduction:
    ALLOWED_LOCALHOST_FILES = {
        "backend/app/core/config.py",     # CORS + REDIS_URL development defaults (documented)
        "backend/app/core/security.py",   # SSRF blocklist: localhost is DENIED there
    }

    def test_localhost_only_in_documented_places(self):
        offenders = []
        for path in (REPO / "backend/app").rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            text = path.read_text(errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(r"localhost|127\.0\.0\.1", line) and rel not in self.ALLOWED_LOCALHOST_FILES:
                    offenders.append(f"{rel}:{i}: {line.strip()[:80]}")
        assert not offenders, "\n".join(offenders)

    def test_no_absolute_developer_paths(self):
        offenders = []
        for path in (REPO / "backend/app").rglob("*.py"):
            text = path.read_text(errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(r"[\"'](/home/|/Users/|C:\\\\)", line):
                    offenders.append(f"{path.relative_to(REPO)}:{i}")
        assert not offenders, offenders

    def test_fake_vton_celery_task_is_gone(self):
        tasks = REPO / "backend/app/workers/tasks.py"
        if tasks.exists():
            tree = ast.parse(tasks.read_text())
            defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            assert "render_vton_task" not in defined, "placeholder VTON renderer must not exist"
            celery = (REPO / "backend/app/workers/celery_app.py").read_text()
            assert "render_vton_task" not in celery

    def test_no_second_vton_renderer_outside_the_modal_worker(self):
        for path in (REPO / "backend/app").rglob("*.py"):
            src = path.read_text(errors="ignore")
            assert "def render_vton" not in src, f"{path} defines a VTON renderer outside services/vton-worker"


class TestDeploymentContractDocument:
    def test_contract_document_exists_and_covers_enforced_variables(self):
        doc = REPO / "docs/PRODUCTION_DEPLOYMENT_CONTRACT.md"
        assert doc.exists(), "docs/PRODUCTION_DEPLOYMENT_CONTRACT.md is missing"
        text = doc.read_text()
        for var in ("ENVIRONMENT", "DATABASE_URL", "SECRET_KEY", "JWT_REFRESH_SECRET",
                    "ENCRYPTION_KEY_FOR_BODY_DATA", "STORAGE_PROVIDER", "VTON_WORKER_URL",
                    "VTON_WORKER_READINESS_URL", "VTON_WORKER_ADMIN_TOKEN", "alembic upgrade head"):
            assert var in text, f"contract does not document {var}"

    def test_dependencies_document_exists(self):
        doc = REPO / "docs/PRODUCTION_DEPENDENCIES.md"
        assert doc.exists()
        text = doc.read_text()
        for dep in ("Neon", "Vercel", "Modal", "Redis", "Gemini", "NVIDIA"):
            assert dep in text

    def test_no_plaintext_secret_values_in_compose_or_docs(self):
        """Published values are refused by the app; they must also not be
        re-published. Placeholders only."""
        from backend.app.core.config import PUBLICLY_KNOWN_SECRET_VALUES

        files = [REPO / "docker-compose.yml", *(REPO / "docs").glob("*.md"), *REPO.glob("*.md")]
        offenders = []
        for f in files:
            if not f.exists():
                continue
            text = f.read_text(errors="ignore")
            for known in PUBLICLY_KNOWN_SECRET_VALUES:
                if known in text and "RELEASE_AUDIT" not in f.name:
                    offenders.append(f"{f.relative_to(REPO)} contains a blocklisted secret value")
        assert not offenders, offenders
