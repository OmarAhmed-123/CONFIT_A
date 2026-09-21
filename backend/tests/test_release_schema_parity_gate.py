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

# Synthetic fixtures, never live revision ids: a reader must be able to tell the
# gate's fixtures from its facts. The live chain is asserted separately, in
# `test_the_real_migration_head_is_a_single_resolvable_revision`, so a rename or
# a second head is caught there rather than by a stale constant here.
#
# They are NUMERICALLY ordered on purpose. Since 2026-09-21 `evaluate` compares
# direction, not just equality, and it orders revisions by the migration chain
# when it knows them and by the leading zero-padded number when it does not —
# which is the case that matters, because production can carry a migration this
# commit has never seen. Fixtures with no ordering signal could not express
# "ahead" at all.
HEAD = "9999_synthetic_newer_revision"
PREV = "9998_synthetic_older_revision"
UNORDERABLE = "synthetic_revision_with_no_number"


def test_parity_passes():
    code, detail = evaluate(HEAD, {"database_revision": HEAD, "verdict": "ok"})
    assert code == 0, detail


def test_production_behind_the_commit_blocks():
    """Exactly the 2026-09-20 incident: main required a revision production lacked."""
    code, detail = evaluate(HEAD, {"database_revision": PREV, "verdict": "ok"})
    assert code == 1
    assert PREV in detail and HEAD in detail
    assert "alembic" in detail  # tells the operator what to do instead of merging


def test_production_ahead_of_the_commit_is_safe_to_merge():
    """2026-09-21: this used to block, and that was the wrong call.

    A preview-branch deployment applied 0018_outfit_share_lifecycle to the
    shared production database while main still expected 0017. This gate
    reported the mismatch as a block, so every merge to main froze behind a
    branch that had nothing to do with it.

    Code that asks only for 0017 runs on a 0018 schema — that is what the
    runtime required-object check verifies per request. "Production is newer
    than this commit" protects nothing by blocking; it just serialises the
    whole repository behind whoever shipped a migration first.

    Still reported, never silently equal: the message says production is AHEAD
    and says the real fix is per-environment databases.
    """
    code, detail = evaluate(PREV, {"database_revision": HEAD, "verdict": "ahead"})
    assert code == 0, detail
    assert "AHEAD" in detail


def test_a_revision_this_tree_has_never_seen_is_read_as_ahead():
    """The exact 2026-09-21 shape: production on a revision main does not know.

    The revision is not in this tree's chain, so it is ordered by its numeric
    prefix. The gate says so out loud rather than presenting an inference as a
    measurement.
    """
    code, detail = evaluate(
        "0017_audit_before_after_request_id",
        {"database_revision": "0018_outfit_share_lifecycle", "verdict": "ahead"},
    )
    assert code == 0, detail
    assert "AHEAD" in detail


def test_revisions_that_cannot_be_ordered_are_indeterminate_never_a_pass():
    """No ordering signal, no direction claim. A gate that guesses is worse than none."""
    code, detail = evaluate(UNORDERABLE, {"database_revision": HEAD})
    assert code == 2, detail
    assert "never passes on a guess" in detail

    code, detail = evaluate(HEAD, {"database_revision": UNORDERABLE})
    assert code == 2, detail


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


def test_the_real_migration_head_is_a_single_resolvable_revision():
    """The gate is only meaningful if the repository has ONE head to compare to.

    Two heads (a merge that forked the chain) would make "the revision this
    commit requires" ambiguous, and the gate would compare against whichever
    one alembic happened to report.
    """
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "backend" / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"migration chain has {len(heads)} heads: {heads}"
