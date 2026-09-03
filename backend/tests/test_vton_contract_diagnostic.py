"""T6 — VTON API ↔ GPU-worker credential contract diagnostic.

Production truth that motivated this: every try-on request returned
``VTON_AUTH_FAILURE`` because the token configured on the API side did not
match the Modal secret ``confit-worker-admin-token``. Nothing in the system
could tell an operator *which* side was wrong without reading the secrets.

``GET /api/v1/health/vton-contract`` (admin-only) sends an intentionally
invalid job with the configured token. The worker authenticates before it
validates the payload, so:

    401  -> token_mismatch
    422  -> consistent (token accepted, payload rejected)
    503  -> consistent_but_worker_not_ready

The endpoint never returns the token. These tests replace the network with an
``httpx`` mock transport that behaves exactly like the real worker
(``services/vton-worker/modal_app.py``: ``X-VTON-Admin`` compared to the
secret, 401 UNAUTHORIZED on mismatch, then Pydantic validation).
"""

import json

import httpx
import pytest

from backend.app.controllers import telemetry_controller as tc
from backend.app.core.config import settings

WORKER_SECRET = "worker-side-secret-value-not-real"
PROCESS = "https://acct--confit-vton-worker-vtoninferenceservice-process.modal.run"


def _fake_worker(worker_ready=True, worker_secret=WORKER_SECRET):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host.endswith("-health.modal.run"):
            return httpx.Response(200, json={
                "status": "healthy", "model": "CatVTON", "model_loaded": worker_ready,
                "segmentation_model": "u2net_human_seg", "mask_engine": "rembg",
                "git_sha": "deadbeef", "device": "Tesla T4", "ready": worker_ready,
            })
        if request.url.host.endswith("-process.modal.run"):
            if request.headers.get("X-VTON-Admin") != worker_secret:
                return httpx.Response(401, json={"detail": "UNAUTHORIZED"})
            if not worker_ready:
                return httpx.Response(503, json={"detail": "VTON_ENGINE_UNAVAILABLE"})
            body = json.loads(request.content or b"{}")
            if not body.get("garments"):
                return httpx.Response(422, json={"detail": [{"loc": ["body", "garments"], "msg": "too short"}]})
            return httpx.Response(200, json={"status": "completed"})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def patched_client(monkeypatch):
    """Route the diagnostic's httpx.AsyncClient through the fake worker."""
    state = {"transport": _fake_worker()}
    real = httpx.AsyncClient

    class _Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = state["transport"]
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "VTON_WORKER_URL", PROCESS, raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_HEALTH_URL", None, raising=False)
    monkeypatch.setattr(settings, "VTON_WORKER_READINESS_URL", None, raising=False)
    monkeypatch.delenv("VTON_WORKER_HEALTH_URL", raising=False)
    monkeypatch.delenv("VTON_WORKER_READINESS_URL", raising=False)
    return state


def _set_api_token(monkeypatch, value):
    monkeypatch.setattr(settings, "VTON_WORKER_ADMIN_TOKEN", value, raising=False)
    monkeypatch.setattr(settings, "CONFIT_WORKER_ADMIN_TOKEN", None, raising=False)
    monkeypatch.delenv("VTON_WORKER_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("CONFIT_WORKER_ADMIN_TOKEN", raising=False)


class TestContractProbe:
    @pytest.mark.asyncio
    async def test_T6_token_mismatch_is_detected_without_revealing_secret(self, patched_client, monkeypatch):
        _set_api_token(monkeypatch, "api-side-DIFFERENT-value")
        r = await tc.probe_vton_worker_contract()
        assert r["contract"] == "token_mismatch"
        assert r["probe_status_code"] == 401
        assert "remediation" in r
        dumped = json.dumps(r)
        assert "api-side-DIFFERENT-value" not in dumped
        assert WORKER_SECRET not in dumped
        # worker metadata is surfaced next to the verdict (deployment drift visible)
        assert r["worker_health"]["git_sha"] == "deadbeef"
        assert r["worker_health"]["segmentation_model"] == "u2net_human_seg"

    @pytest.mark.asyncio
    async def test_matching_token_is_reported_consistent(self, patched_client, monkeypatch):
        _set_api_token(monkeypatch, WORKER_SECRET)
        r = await tc.probe_vton_worker_contract()
        assert r["contract"] == "consistent"
        assert r["probe_status_code"] == 422
        assert WORKER_SECRET not in json.dumps(r)

    @pytest.mark.asyncio
    async def test_matching_token_but_model_not_loaded(self, patched_client, monkeypatch):
        patched_client["transport"] = _fake_worker(worker_ready=False)
        _set_api_token(monkeypatch, WORKER_SECRET)
        r = await tc.probe_vton_worker_contract()
        assert r["contract"] == "consistent_but_worker_not_ready"

    @pytest.mark.asyncio
    async def test_missing_api_token_is_its_own_verdict(self, patched_client, monkeypatch):
        _set_api_token(monkeypatch, None)
        r = await tc.probe_vton_worker_contract()
        assert r["contract"] == "token_missing_on_api"
        assert r["token_configured"] is False

    @pytest.mark.asyncio
    async def test_unconfigured_worker(self, monkeypatch):
        monkeypatch.setattr(settings, "VTON_WORKER_URL", None, raising=False)
        monkeypatch.delenv("VTON_WORKER_URL", raising=False)
        r = await tc.probe_vton_worker_contract()
        assert r["contract"] == "worker_not_configured"

    @pytest.mark.asyncio
    async def test_unreachable_worker_is_reported_not_faked(self, patched_client, monkeypatch):
        def boom(request):
            raise httpx.ConnectError("no route", request=request)
        patched_client["transport"] = httpx.MockTransport(boom)
        _set_api_token(monkeypatch, WORKER_SECRET)
        r = await tc.probe_vton_worker_contract()
        assert r["contract"] == "worker_unreachable"
        assert "error" in r["worker_health"]


class TestEndpointAccessControl:
    def _login(self, client, email):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_anonymous_gets_401(self, client):
        assert client.get("/api/v1/health/vton-contract").status_code == 401

    def test_consumer_gets_403(self, client):
        h = self._login(client, "shopper@confit.io")
        assert client.get("/api/v1/health/vton-contract", headers=h).status_code == 403

    def test_admin_gets_verdict_and_no_token_in_body(self, client, patched_client, monkeypatch):
        _set_api_token(monkeypatch, "api-side-DIFFERENT-value")
        h = self._login(client, "admin@confit.io")
        r = client.get("/api/v1/health/vton-contract", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["contract"] == "token_mismatch"
        assert "api-side-DIFFERENT-value" not in r.text

    def test_endpoint_hidden_from_openapi(self):
        from backend.app.main import app
        assert "/api/v1/health/vton-contract" not in app.openapi()["paths"]


class TestT4RevisionConsistency:
    """T4 — deployed Modal revision vs intended Git SHA. Pure verdict logic plus
    the live path through the diagnostic (fake worker reports 'deadbeef')."""

    def _clear(self, monkeypatch):
        monkeypatch.setattr(settings, "VTON_WORKER_EXPECTED_GIT_SHA", None, raising=False)
        monkeypatch.delenv("VTON_WORKER_EXPECTED_GIT_SHA", raising=False)
        monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)

    def test_match_requires_same_commit(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("VTON_WORKER_EXPECTED_GIT_SHA", "c928544f73ca1407824dca95b3a5ccfbcf73742e")
        assert tc._revision_verdict("c928544f73ca1407824dca95b3a5ccfbcf73742e")["verdict"] == "match"
        assert tc._revision_verdict("c928544f73ca")["verdict"] == "match"          # abbreviated form
        assert tc._revision_verdict("3c9e9e76fad6f2179692c495ab46304b90b6e673")["verdict"] == "mismatch"

    def test_short_prefix_cannot_fake_a_match(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("VTON_WORKER_EXPECTED_GIT_SHA", "c928544f73ca1407824dca95b3a5ccfbcf73742e")
        assert tc._revision_verdict("c92")["verdict"] == "mismatch"

    def test_unknown_and_dirty_are_never_a_pass(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("VTON_WORKER_EXPECTED_GIT_SHA", "c928544f73ca1407824dca95b3a5ccfbcf73742e")
        assert tc._revision_verdict(None)["verdict"] == "worker_unknown"
        assert tc._revision_verdict("unknown")["verdict"] == "worker_unknown"
        assert tc._revision_verdict("c928544f73ca1407824dca95b3a5ccfbcf73742e-dirty")["verdict"] == "dirty_deploy"

    def test_falls_back_to_vercel_commit_sha(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "deadbeefcafe0000")
        assert tc._revision_verdict("deadbeefcafe0000")["verdict"] == "match"
        assert tc._revision_verdict("0badf00d0badf00d")["verdict"] == "mismatch"

    def test_no_expected_sha_is_reported_not_passed(self, monkeypatch):
        self._clear(monkeypatch)
        assert tc._revision_verdict("deadbeefcafe0000")["verdict"] == "no_expected_sha"

    @pytest.mark.asyncio
    async def test_T4_diagnostic_reports_mismatch_against_fake_worker(self, patched_client, monkeypatch):
        self._clear(monkeypatch)
        _set_api_token(monkeypatch, WORKER_SECRET)
        monkeypatch.setenv("VTON_WORKER_EXPECTED_GIT_SHA", "1111111111111111111111111111111111111111")
        r = await tc.probe_vton_worker_contract()
        assert r["contract"] == "consistent"
        assert r["revision"]["worker_git_sha"] == "deadbeef"
        assert r["revision"]["verdict"] == "mismatch"
        monkeypatch.setenv("VTON_WORKER_EXPECTED_GIT_SHA", "deadbeef")
        r = await tc.probe_vton_worker_contract()
        assert r["revision"]["verdict"] == "match"

    def test_endpoint_hidden_from_openapi_still(self):
        from backend.app.main import app
        assert "/api/v1/health/vton-contract" not in app.openapi()["paths"]
