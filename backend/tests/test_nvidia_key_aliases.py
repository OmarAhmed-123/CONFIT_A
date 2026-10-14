"""NVIDIA credential discovery must not depend on how an operator named the vars.

MEASURED 2026-10-14: an operator env file with nineteen live per-model keys
(`NVIDIA_API_KEY_KIMI_K3`, …) produced `slots_missing: 19` from a pool that reads
`NVIDIA_KEY_KIMI_K3`, so `/health` reported NVIDIA unconfigured while nineteen
valid credentials sat in the environment. These tests hold both namings open, and
they hold the safety property that made the aliasing acceptable in the first
place: an alias is only read if it still looks like an NVIDIA key.
"""
from __future__ import annotations

import os

import pytest

from backend.app.providers.nvidia.keypool import (
    SLOT_KEY_ENV_ALIASES,
    SLOT_KEY_ENV_VARS,
    NvidiaKeyPool,
    alias_env_names,
)

#: Satisfies the `nvapi-` gate and is obviously not a credential.
FAKE_KEY = "nvapi-" + "0" * 60
OTHER_KEY = "nvapi-" + "1" * 60

NVIDIA_VARS = tuple(
    name for name in os.environ if name.startswith("NVIDIA")
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """No ambient NVIDIA variable may decide the outcome of these tests."""
    for name in NVIDIA_VARS + tuple(
        n for n in os.environ if n.startswith("NVIDIA")
    ):
        monkeypatch.delenv(name, raising=False)
    yield


# ── the alias table itself ───────────────────────────────────────────────────

def test_every_slot_is_reachable_under_both_namings():
    for slot in SLOT_KEY_ENV_VARS:
        asserted = alias_env_names(slot)
        assert asserted, f"{slot} has no alternate name"
        assert slot not in asserted, "an alias must not repeat the canonical name"
        assert all(name.startswith("NVIDIA_") for name in asserted)


def test_mechanical_rule_maps_the_slot_naming_onto_the_platform_naming():
    assert "NVIDIA_API_KEY_KIMI_K3" in alias_env_names("NVIDIA_KEY_KIMI_K3")
    assert "NVIDIA_API_KEY_GLM_5_3_FLASH" in alias_env_names("NVIDIA_KEY_GLM_5_3_FLASH")


def test_the_four_non_mechanical_pairs_are_carried_explicitly():
    """A rename that does not follow the rule is a decision, not a derivation."""
    assert alias_env_names("NVIDIA_KEY_ISING_CALIBRATION_1_5_31B") == (
        "NVIDIA_API_KEY_ISING_CALIBRATION_1_5_31B",
        "NVIDIA_API_KEY_ISING_CALIBRATION_A",
    )
    assert "NVIDIA_API_KEY_ISING_CALIBRATION_B" in alias_env_names(
        "NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2"
    )
    assert "NVIDIA_API_KEY_DIFFUSIONGEMMA_26B_A4B" in alias_env_names(
        "NVIDIA_KEY_DIFFUSIONGEMMA_26B_A4B_IT"
    )
    assert "NVIDIA_API_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B" in alias_env_names(
        "NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING"
    )
    # the two ISING slots must not collapse onto one name — they are two keys
    assert set(alias_env_names("NVIDIA_KEY_ISING_CALIBRATION_1_5_31B")) & set(
        alias_env_names("NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2")
    ) == set()


def test_alias_table_only_names_slots_that_exist():
    unknown = set(SLOT_KEY_ENV_ALIASES) - set(SLOT_KEY_ENV_VARS)
    assert not unknown, f"alias table references unknown slots: {sorted(unknown)}"


# ── discovery ────────────────────────────────────────────────────────────────

def test_a_slot_is_satisfied_by_the_platform_naming(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY_KIMI_K3", FAKE_KEY)
    pool = NvidiaKeyPool()

    assert pool.slot("NVIDIA_KEY_KIMI_K3") == FAKE_KEY
    assert pool.configured is True
    status = pool.status()
    assert status["slots_present"] == ["NVIDIA_KEY_KIMI_K3"]
    # `status()` reports both lists sorted, so compare as sets rather than
    # pretending to know the order.
    assert set(status["slots_missing"]) == set(SLOT_KEY_ENV_VARS) - {"NVIDIA_KEY_KIMI_K3"}
    # and the report says WHERE it came from, so a rename is visible in /health
    assert status["aliased_slots"] == {"NVIDIA_KEY_KIMI_K3": "NVIDIA_API_KEY_KIMI_K3"}


def test_the_canonical_name_still_wins_when_both_are_present(monkeypatch):
    monkeypatch.setenv("NVIDIA_KEY_KIMI_K3", FAKE_KEY)
    monkeypatch.setenv("NVIDIA_API_KEY_KIMI_K3", OTHER_KEY)
    pool = NvidiaKeyPool()

    assert pool.slot("NVIDIA_KEY_KIMI_K3") == FAKE_KEY
    assert pool.alias_sources() == {}, "an alias must not be credited when the slot is set"


def test_the_non_mechanical_pairs_resolve_to_distinct_slots(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY_ISING_CALIBRATION_A", FAKE_KEY)
    monkeypatch.setenv("NVIDIA_API_KEY_ISING_CALIBRATION_B", OTHER_KEY)
    pool = NvidiaKeyPool()

    assert pool.slot("NVIDIA_KEY_ISING_CALIBRATION_1_5_31B") == FAKE_KEY
    assert pool.slot("NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2") == OTHER_KEY
    assert pool.size() == 2, "two keys must stay two credentials in the rotation"


def test_an_alias_still_has_to_look_like_a_key(monkeypatch):
    """The gate that keeps a stray non-credential out of the pool is not relaxed."""
    monkeypatch.setenv("NVIDIA_API_KEY_KIMI_K3", "not-a-key")
    pool = NvidiaKeyPool()

    assert pool.configured is False
    assert pool.slot("NVIDIA_KEY_KIMI_K3") is None


def test_legacy_names_are_unaffected(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)
    pool = NvidiaKeyPool()

    assert pool.status()["legacy_present"] == ["NVIDIA_API_KEY"]
    # NVIDIA_API_KEY is not the mechanical alias of any slot name, so it must not
    # be mistaken for one: `NVIDIA_API_KEY_<MODEL>` is a prefix match, not this.
    assert pool.status()["slots_present"] == []


def test_a_pool_only_deployment_counts_as_configured(monkeypatch):
    """`/health` and the orchestrator ask the pool, not a legacy shared key."""
    monkeypatch.setenv("NVIDIA_API_KEY_KIMI_K3", FAKE_KEY)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_CHAT_KEY_2", raising=False)

    from backend.app.providers.nvidia import key_pool
    from backend.app.providers.orchestrator import MultiProviderAIOrchestrator

    key_pool.reload()
    try:
        assert key_pool.configured is True
        assert MultiProviderAIOrchestrator._nvidia_pool_configured() is True
    finally:
        key_pool.reload()  # leave the module singleton as the environment found it


def test_readiness_probes_the_pool_and_not_only_the_legacy_key(monkeypatch):
    from backend.app.core.config import settings
    from backend.app.providers.nvidia import key_pool
    from backend.app.services import ai_readiness

    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "NVIDIA_CHAT_KEY_2", "", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY_KIMI_K3", FAKE_KEY)
    key_pool.reload()
    try:
        configured = ai_readiness._configured_providers()
        assert "nvidia" in configured, "nineteen keys is not 'not configured'"
        assert configured["nvidia"]["auth"] == f"Bearer {FAKE_KEY}"
        assert "nvidia" in ai_readiness.configured_provider_names()
    finally:
        key_pool.reload()


def test_no_credential_value_is_ever_reported(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY_KIMI_K3", FAKE_KEY)
    pool = NvidiaKeyPool()

    import json

    payload = json.dumps(pool.status(), default=str)
    assert FAKE_KEY not in payload
    assert FAKE_KEY not in repr(pool)
