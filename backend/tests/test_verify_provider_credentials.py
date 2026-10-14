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
