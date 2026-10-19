"""The credential verifier has to be safe to run against production credentials.

Three properties matter more than the probes themselves, because the tool is
pointed at real keys:

1. it never prints or serialises a secret value;
2. it never writes anything to a provider (read-only GETs and protocol
   handshakes only — no mail, no upload, no DNS change, no GPU job);
3. its exit code is a usable gate (0 answered / 1 a configured credential failed
   / 2 nothing configured).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.scripts import verify_provider_credentials as vpc

FAKE_SECRET = "nvapi-" + "z" * 48


# ── 1 · no secret escapes the report ─────────────────────────────────────────

def test_render_prints_names_and_fingerprints_but_never_values(capsys):
    result = vpc.Result(
        provider="nvidia",
        capability="kimi-k3",
        status=vpc.OK,
        detail="HTTP 200",
        name="NVIDIA_API_KEY_KIMI_K3",
        fingerprint=vpc.Vault.fingerprint(FAKE_SECRET),
        latency_ms=42,
    )
    vpc.render([result])
    printed = capsys.readouterr().out

    assert FAKE_SECRET not in printed
    assert "NVIDIA_API_KEY_KIMI_K3" in printed
    assert vpc.Vault.fingerprint(FAKE_SECRET) in printed


def test_the_json_report_carries_no_value():
    result = vpc.Result(
        provider="smtp", capability="outbound mail", status=vpc.OK, detail="STARTTLS + AUTH ok",
        name="SMTP_HOST", fingerprint=vpc.Vault.fingerprint(FAKE_SECRET),
    )
    payload = json.dumps(result.as_dict())
    assert FAKE_SECRET not in payload
    assert "fingerprint" in payload


def test_identical_values_are_visible_by_fingerprint_only():
    assert vpc.Vault.fingerprint(FAKE_SECRET) == vpc.Vault.fingerprint(FAKE_SECRET)
    assert vpc.Vault.fingerprint(FAKE_SECRET) != vpc.Vault.fingerprint(FAKE_SECRET + "x")
    assert len(vpc.Vault.fingerprint(FAKE_SECRET)) == 8


# ── 2 · read-only, by construction ───────────────────────────────────────────

def test_the_verifier_contains_no_mutating_http_call():
    source = Path(vpc.__file__).read_text(encoding="utf-8")
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert f'"{verb}"' not in source, f"{verb} is a write and has no place in this tool"
        assert f"'{verb}'" not in source
    assert "client.post" not in source
    assert "requests.post" not in source


def test_smtp_probe_never_sends_a_message():
    source = Path(vpc.__file__).read_text(encoding="utf-8")
    assert "sendmail" not in source
    assert "send_message" not in source
    assert "starttls" in source and "login(" in source, "handshake + AUTH is the whole probe"


# ── 3 · verdicts and exit codes ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, {}, vpc.OK),
        (204, None, vpc.OK),
        (401, {}, vpc.AUTH_FAILED),
        (403, {}, vpc.AUTH_FAILED),
        (404, {"error": "not found"}, vpc.HTTP_ERROR),
        (500, "boom", vpc.HTTP_ERROR),
        (0, None, vpc.UNREACHABLE),
    ],
)
def test_http_verdicts(status, body, expected):
    assert vpc.classify_http(status, body)[0] == expected


# A DSN carrying an embedded password is exactly what this repository's own
# gitleaks rule (`database-dsn-with-password`, .gitleaks.toml) exists to catch,
# and "it is only a test fixture" is not a good enough reason to weaken it — so
# the fixture is assembled instead of written as one literal. The value is
# fabricated; the assertion below is what matters, and it needs a value long
# enough to be worth masking.
FIXTURE_PASSWORD = "not-a-real-" + "password"
FIXTURE_DSN = (
    "postgresql://fixture_user:" + FIXTURE_PASSWORD
    + "@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require"
)


def test_database_urls_are_described_without_the_password():
    described = vpc.describe_database(FIXTURE_DSN)

    assert described["host"] == "ep-x.eu-central-1.aws.neon.tech"
    assert described["database"] == "neondb"
    assert described["user"] == "fixture_user"
    assert FIXTURE_PASSWORD not in json.dumps(described)


def test_failure_exit_code_when_a_configured_credential_is_rejected(monkeypatch, capsys):
    async def fake_run(selected):
        return [vpc.Result("neon", "primary", vpc.AUTH_FAILED, "HTTP 401", "DATABASE_URL", "abcd1234")]

    monkeypatch.setattr(vpc, "run", fake_run)
    assert vpc.main(["--quiet"]) == 1


def test_exit_code_two_when_nothing_is_configured(monkeypatch, capsys):
    async def fake_run(selected):
        return [vpc.Result("openai", "chat", vpc.NOT_CONFIGURED, "OPENAI_API_KEY is not set")]

    monkeypatch.setattr(vpc, "run", fake_run)
    assert vpc.main(["--quiet"]) == 2


def test_exit_code_zero_when_every_configured_probe_answered(monkeypatch, capsys):
    async def fake_run(selected):
        return [
            vpc.Result("github", "repository", vpc.OK, "HTTP 200", "GITHUB_TOKEN", "abcd1234"),
            vpc.Result("modal", "workers", vpc.SHAPE_ONLY, "pair present", "MODAL_TOKEN_ID", "efgh5678"),
            vpc.Result("dnshe", "dns", vpc.ENDPOINT_UNKNOWN, "not verified", "DNSHE_API_KEY", "ijkl9012"),
            vpc.Result("openai", "chat", vpc.NOT_CONFIGURED, "not set"),
        ]

    monkeypatch.setattr(vpc, "run", fake_run)
    assert vpc.main(["--quiet"]) == 0


def test_every_probe_group_is_named_and_reachable():
    names = [name for name, _ in vpc.PROBE_GROUPS]
    assert len(names) == len(set(names)), "a group name must select exactly one group"
    assert {"nvidia", "neon", "s3", "smtp", "fx"} <= set(names)


def test_json_report_is_written_and_holds_no_credentials(monkeypatch, tmp_path, capsys):
    async def fake_run(selected):
        return [vpc.Result("groq", "failover", vpc.OK, "HTTP 200", "GROQ_API_KEY",
                           vpc.Vault.fingerprint(FAKE_SECRET))]

    monkeypatch.setattr(vpc, "run", fake_run)
    target = tmp_path / "report.json"
    assert vpc.main(["--json", str(target), "--quiet"]) == 0
    text = target.read_text(encoding="utf-8")
    assert FAKE_SECRET not in text
    payload = json.loads(text)
    assert payload["probes"][0]["provider"] == "groq"
    assert payload["totals"] == {"ok": 1}


# ── environment precedence ───────────────────────────────────────────────────

def test_process_environment_wins_over_a_dotenv_file(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=from-file\nGEMINI_API_KEY=file-only\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    monkeypatch.setenv("OPENAI_API_KEY", "from-environment")

    vault = vpc.Vault()
    assert vault.get("OPENAI_API_KEY") == ("from-environment", "OPENAI_API_KEY")
    assert vault.get("GEMINI_API_KEY") == ("file-only", "GEMINI_API_KEY")


def test_blank_values_do_not_count_as_configured(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert vpc.Vault().get("OPENAI_API_KEY") == (None, None)


def test_the_supplied_nvidia_slots_all_have_an_accepted_name():
    """The harness' slot table and the pool's alias table must agree."""
    from backend.app.providers.nvidia.keypool import SLOT_KEY_ENV_VARS, alias_env_names

    mapped = {}
    for canonical, alias, _model in vpc.NVIDIA_SLOTS:
        mapped[canonical] = alias
    assert set(mapped) <= set(SLOT_KEY_ENV_VARS), "the harness maps a slot the pool does not know"
    for canonical, alias in mapped.items():
        assert alias == canonical or alias in alias_env_names(canonical), (
            f"{alias} is not an accepted name for {canonical}"
        )


def test_no_slot_table_entry_is_left_uncovered():
    """Every pool slot the operator supplied a key for is probed by the harness."""
    from backend.app.providers.nvidia.keypool import SLOT_KEY_ENV_VARS

    probed = {canonical for canonical, _alias, _model in vpc.NVIDIA_SLOTS}
    assert set(SLOT_KEY_ENV_VARS) - probed == set(), "a slot key would go unverified"


def test_the_ising_pair_is_not_collapsed():
    ising = [row for row in vpc.NVIDIA_SLOTS if "ISING" in row[0]]
    assert len(ising) == 2
    assert ising[0][1] != ising[1][1]
    assert re.search(r"_A$", ising[0][1]) and re.search(r"_B$", ising[1][1])


# ── operator env-name spellings ──────────────────────────────────────────────
# REGRESSION (Slice C). The verifier reported "not configured" for credentials
# the operator had in fact supplied, because it looked for one spelling only.
# A report that says "absent" about a key that is present is worse than no
# report: it sends someone hunting for a credential they already own.

def test_glitchtip_is_found_under_the_operator_spelling(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("GLITCHTIP_TOKEN=" + "g" * 64 + "\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    monkeypatch.delenv("GLITCHTIP_KEY", raising=False)
    monkeypatch.delenv("GLITCHTIP_TOKEN", raising=False)

    import asyncio
    rows = asyncio.run(vpc.probe_sentry(vpc.Vault()))
    glitch = [r for r in rows if r.provider == "glitchtip"]
    assert len(glitch) == 1
    assert glitch[0].status != vpc.NOT_CONFIGURED, "a supplied key must never be reported absent"
    assert glitch[0].name == "GLITCHTIP_TOKEN"
    # A bare project key has no host/project, so no endpoint can be called.
    assert glitch[0].status == vpc.SKIPPED


def test_confit_hub_is_found_under_the_operator_spelling(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("CONFITHUB_API_KEY=" + "c" * 50 + "\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    for name in ("CONFIT_HUB_API_KEY", "CONFITHUB_API_KEY", "VERCEL_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    import asyncio
    rows = asyncio.run(vpc.probe_platforms(vpc.Vault()))
    hub = [r for r in rows if r.provider == "confit-hub"]
    assert len(hub) == 1
    assert hub[0].status != vpc.NOT_CONFIGURED
    assert hub[0].name == "CONFITHUB_API_KEY"


def test_a_sentry_dsn_token_is_reported_as_a_gap_not_as_configured(monkeypatch, tmp_path):
    """A DSN token cannot authenticate the API. Saying "not configured" hides a
    real, supplied credential; saying "ok" would be a lie. SKIPPED + the reason."""
    (tmp_path / ".env").write_text("SENTRY_DSN_TOKEN=" + "s" * 71 + "\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("SENTRY_DSN_TOKEN", raising=False)

    import asyncio
    rows = asyncio.run(vpc.probe_sentry(vpc.Vault()))
    sentry = [r for r in rows if r.provider == "sentry"][0]
    assert sentry.status == vpc.SKIPPED
    assert sentry.name == "SENTRY_DSN_TOKEN"
    assert "not an API auth token" in sentry.detail


# ── PSP seam (spec 012) ──────────────────────────────────────────────────────

def test_payments_probe_reports_no_charge_path_when_nothing_is_configured(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    for var, _ in vpc.PSP_CREDENTIALS:
        monkeypatch.delenv(var, raising=False)

    import asyncio
    rows = asyncio.run(vpc.probe_payments(vpc.Vault()))
    assert len(rows) == 1
    assert rows[0].status == vpc.SKIPPED
    assert "demo mode" in rows[0].detail


def test_payments_is_a_registered_probe_group():
    assert "payments" in [name for name, _ in vpc.PROBE_GROUPS]


def test_no_probe_in_the_payments_group_mutates(monkeypatch, tmp_path):
    """The PSP probe must never POST: a credential check that creates a charge
    is not a credential check."""
    source = Path(vpc.__file__).read_text(encoding="utf-8")
    block = source.split("async def probe_payments", 1)[1].split("\nasync def ", 1)[0]
    for verb in ("post", "put", "patch", "delete"):
        assert f".{verb}(" not in block


# ── Brevo sender verification ────────────────────────────────────────────────

def test_brevo_reports_active_senders(monkeypatch):
    calls = []

    async def fake_probe_http(provider, capability, url, *, headers=None, value=None,
                              name=None, capture=None, **kw):
        calls.append(url)
        if url.endswith("/v3/account"):
            return vpc.Result(provider, capability, vpc.OK, "HTTP 200", name, "deadbeef")
        if capture is not None:
            capture["body"] = [
                {"email": "shop@confit.example", "active": True},
                {"email": "old@confit.example", "active": False},
            ]
        return vpc.Result(provider, capability, vpc.OK, "HTTP 200", name, "deadbeef")

    monkeypatch.setattr(vpc, "probe_http", fake_probe_http)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-" + "a" * 30)

    import asyncio
    rows = asyncio.run(vpc.probe_brevo_api(vpc.Vault()))
    assert "https://api.brevo.com/v3/senders" in calls
    sender = [r for r in rows if "sender" in r.capability][0]
    assert sender.extra["active_senders"] == ["shop@confit.example"]
    assert "1 active sender" in sender.detail


def test_brevo_warns_when_no_sender_is_active(monkeypatch):
    async def fake_probe_http(provider, capability, url, *, headers=None, value=None,
                              name=None, capture=None, **kw):
        if capture is not None:
            capture["body"] = [{"email": "old@confit.example", "active": False}]
        return vpc.Result(provider, capability, vpc.OK, "HTTP 200", name, "deadbeef")

    monkeypatch.setattr(vpc, "probe_http", fake_probe_http)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-" + "a" * 30)

    import asyncio
    rows = asyncio.run(vpc.probe_brevo_api(vpc.Vault()))
    sender = [r for r in rows if "sender" in r.capability][0]
    assert "NO active sender" in sender.detail


def test_probe_http_capture_never_stores_the_credential():
    """The capture hook exists to inspect payloads; it must not become a second
    place a secret can land."""
    import inspect
    sig = inspect.signature(vpc.probe_http)
    assert "capture" in sig.parameters
    source = inspect.getsource(vpc.probe_http)
    assert 'capture["body"]' in source
    assert "capture[\"value\"]" not in source


# ── REGRESSION: Brevo's documented payload shape ─────────────────────────────
# Measured 2026-10-19: GET /v3/senders answers {"senders": [ {...} ]}. An
# earlier version of this probe read the bare-list shape only and therefore
# reported "NO active sender" for an account that had one — a false FAIL on
# the mail path. Both shapes must be understood, and an unrecognised shape
# must say so instead of being read as zero.

def _brevo_probe_with(captured_body):
    async def fake_probe_http(provider, capability, url, *, headers=None, value=None,
                              name=None, capture=None, **kw):
        if capture is not None:
            capture["body"] = captured_body
        return vpc.Result(provider, capability, vpc.OK, "HTTP 200", name, "deadbeef")
    return fake_probe_http


def test_brevo_reads_the_documented_senders_object_shape(monkeypatch):
    monkeypatch.setattr(vpc, "probe_http", _brevo_probe_with(
        {"senders": [{"email": "shop@confit.example", "active": True}]}
    ))
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-" + "a" * 30)

    import asyncio
    rows = asyncio.run(vpc.probe_brevo_api(vpc.Vault()))
    sender = [r for r in rows if "sender" in r.capability][0]
    assert sender.extra["active_senders"] == ["shop@confit.example"]
    assert "NO active sender" not in sender.detail


def test_brevo_unrecognised_payload_is_not_read_as_zero_senders(monkeypatch):
    monkeypatch.setattr(vpc, "probe_http", _brevo_probe_with({"unexpected": "shape"}))
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-" + "a" * 30)

    import asyncio
    rows = asyncio.run(vpc.probe_brevo_api(vpc.Vault()))
    sender = [r for r in rows if "sender" in r.capability][0]
    assert sender.status == vpc.ENDPOINT_UNKNOWN
    assert "not the documented" in sender.detail


# ── REGRESSION: Neon DSN slot naming ────────────────────────────────────────
# The operator stores <role>_<database>; the table assumed <database>_<role>.
# Four of five slots printed "not configured" for DSNs that were configured.

def test_neon_slots_accept_the_operator_role_first_spelling(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "DATABASE_URL_OWNER_NEONDB=postgresql://u:p@example.invalid:5432/neondb\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    for names, _ in vpc.DATABASES:
        for n in names:
            monkeypatch.delenv(n, raising=False)

    import asyncio
    # Only assert name resolution: the host is deliberately unresolvable, so the
    # probe must report unreachable rather than not_configured.
    rows = asyncio.run(vpc.probe_databases(vpc.Vault()))
    owner = [r for r in rows if "owner" in r.capability][0]
    assert owner.status != vpc.NOT_CONFIGURED, "a configured DSN must never be reported absent"


def test_every_database_slot_declares_at_least_one_name():
    for names, label in vpc.DATABASES:
        assert names and all(isinstance(n, str) and n for n in names), label


# ── REGRESSION: one provider's credentials must never be tried against
#    another provider's endpoint ──────────────────────────────────────────────
# RunPod's access key was presented to the AWS endpoint (both targets shared
# AWS_ENDPOINT_URL_S3), so a valid key came back `auth_failed`. That reads as
# "your credential is bad" when the probe simply asked the wrong server.

def test_runpod_s3_does_not_borrow_the_aws_endpoint(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "RUNPOD_S3_ACCESS_KEY=ak\nRUNPOD_S3_SECRET_KEY=sk\n"
        "AWS_ENDPOINT_URL_S3=https://s3.example.invalid\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    for n in ("RUNPOD_S3_ACCESS_KEY", "RUNPOD_S3_SECRET_KEY", "AWS_ENDPOINT_URL_S3",
              "RUNPOD_S3_ENDPOINT_URL", "RUNPOD_ENDPOINT_URL", "AWS_ACCESS_KEY_ID",
              "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(n, raising=False)

    import asyncio
    rows = asyncio.run(vpc.probe_s3_compatible(vpc.Vault()))
    runpod = [r for r in rows if "RunPod" in r.capability][0]
    assert runpod.status == vpc.SHAPE_ONLY, "must not be probed against the AWS host"
    assert runpod.status != vpc.AUTH_FAILED
    assert "no endpoint of its own" in runpod.detail


def test_runpod_s3_uses_its_own_endpoint_when_one_is_configured(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "RUNPOD_S3_ACCESS_KEY=ak\nRUNPOD_S3_SECRET_KEY=sk\n"
        "RUNPOD_S3_ENDPOINT_URL=https://runpod.example.invalid\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    for n in ("RUNPOD_S3_ACCESS_KEY", "RUNPOD_S3_SECRET_KEY", "RUNPOD_S3_ENDPOINT_URL",
              "AWS_ENDPOINT_URL_S3", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(n, raising=False)

    vault = vpc.Vault()
    assert vault.get("RUNPOD_S3_ENDPOINT_URL")[0] == "https://runpod.example.invalid"
    # Resolution only: the host is .invalid, so the probe cannot reach it.
    import asyncio
    rows = asyncio.run(vpc.probe_s3_compatible(vault))
    runpod = [r for r in rows if "RunPod" in r.capability][0]
    assert runpod.status != vpc.NOT_CONFIGURED


# ── REGRESSION: "not configured" vs "spelled wrong" ─────────────────────────
# The operator supplied keys like NVIDIA_API_KEY_NEMOTRON_3_ULTRA while the app
# reads NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B. Reporting only "not configured"
# sends someone to buy a credential they already have.

def test_near_miss_finds_an_abbreviated_operator_name(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("NVIDIA_API_KEY_NEMOTRON_3_ULTRA=nvapi-abc\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    monkeypatch.delenv("NVIDIA_API_KEY_NEMOTRON_3_ULTRA", raising=False)

    vault = vpc.Vault()
    hit = vpc.near_miss(("NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B",
                         "NVIDIA_API_KEY_NEMOTRON_3_ULTRA_550B_A55B"), vault)
    assert hit == "NVIDIA_API_KEY_NEMOTRON_3_ULTRA"


def test_near_miss_does_not_conflate_two_distinct_models(monkeypatch, tmp_path):
    """GLM_5_3 and GLM_5_3_FLASH are different models, not one misspelt name."""
    (tmp_path / ".env").write_text("NVIDIA_API_KEY_GLM_5_3_FLASH=nvapi-abc\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    monkeypatch.delenv("NVIDIA_API_KEY_GLM_5_3_FLASH", raising=False)

    vault = vpc.Vault()
    assert vpc.near_miss(("NVIDIA_KEY_GLM_5_3", "NVIDIA_API_KEY_GLM_5_3"), vault) is None


def test_configured_names_never_returns_values(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("SOME_TOKEN=supersecretvalue\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    monkeypatch.delenv("SOME_TOKEN", raising=False)

    names = vpc.Vault().configured_names()
    assert "SOME_TOKEN" in names
    assert all("supersecretvalue" not in n for n in names)


def test_unread_nvidia_names_are_enumerated_not_guessed(monkeypatch, tmp_path):
    """Every operator key that no slot consumes must be listed by NAME, so
    "19 keys supplied, 8 in use" is answerable from the report."""
    (tmp_path / ".env").write_text(
        "NVIDIA_API_KEY_TOTALLY_UNKNOWN_MODEL=nvapi-aaa\n"
        "NVIDIA_API_KEY_CONTENT_SAFETY=nvapi-bbb\n", encoding="utf-8")
    monkeypatch.setattr(vpc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(vpc, "DOTENV_CANDIDATES", (".env",))
    for canonical, alias, _m in vpc.NVIDIA_SLOTS:
        for n in (canonical, alias):
            monkeypatch.delenv(n, raising=False)
    for n in ("NVIDIA_API_KEY_TOTALLY_UNKNOWN_MODEL", "NVIDIA_API_KEY_CONTENT_SAFETY",
              "NVIDIA_API_KEY", "NVIDIA_CHAT_KEY_2"):
        monkeypatch.delenv(n, raising=False)

    import asyncio
    rows = asyncio.run(vpc.probe_nvidia(vpc.Vault()))
    unread = [r for r in rows if r.capability == "keys present but read by no slot"]
    assert len(unread) == 1
    names = unread[0].extra["unread_names"]
    assert "NVIDIA_API_KEY_CONTENT_SAFETY" in names
    assert "NVIDIA_API_KEY_TOTALLY_UNKNOWN_MODEL" in names
    # names only — never a value
    assert "nvapi-aaa" not in unread[0].detail
