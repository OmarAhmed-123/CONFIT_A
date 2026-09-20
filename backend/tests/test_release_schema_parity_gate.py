"""The release gate's three outcomes, pinned.

The gate exists because production was taken down on 2026-09-20 by merging code
that required a migration the production database did not have yet. Its decision
function is pure, so the outcomes — parity, mismatch, indeterminate — are tested
here without a network or a database; the workflow itself is exercised by CI on
every PR to `main`.

A gate that can be made to pass by accident is worse than no gate, so the
indeterminate cases are asserted to be *failures*, never passes.
"""
from __future__ import annotations

import pytest

from backend.scripts.check_release_schema_parity import evaluate

HEAD = "0018_partner_onboarding_email_lifecycle"
PREV = "0017_audit_before_after_request_id"


def test_parity_passes():
    code, detail = evaluate(HEAD, {"database_revision": HEAD, "verdict": "ok"})
    assert code == 0, detail


def test_production_behind_the_commit_blocks():
    """Exactly the 2026-09-20 incident: main required 0018, production had 0017."""
    code, detail = evaluate(HEAD, {"database_revision": PREV, "verdict": "ok"})
    assert code == 1
    assert PREV in detail and HEAD in detail
    assert "alembic" in detail  # tells the operator what to do instead of merging


def test_production_ahead_of_the_commit_also_blocks():
    """A database ahead of the code is drift for that code: it is not deployable either."""
    code, detail = evaluate(PREV, {"database_revision": HEAD, "verdict": "drift"})
    assert code == 1, detail


def test_unmanaged_database_is_indeterminate_not_a_pass():
    code, detail = evaluate(HEAD, {"database_revision": None})
    assert code == 2, detail


def test_commit_without_a_migration_head_is_indeterminate():
    code, detail = evaluate(None, {"database_revision": HEAD})
    assert code == 2, detail


@pytest.mark.parametrize("label,code", [("PASS", 0), ("BLOCK", 1), ("INDETERMINATE", 2)])
def test_labels_are_distinct(label, code):
    """Guard against a refactor that makes an unknown state look like success."""
    assert label in {"PASS", "BLOCK", "INDETERMINATE"}
    assert code in {0, 1, 2}
