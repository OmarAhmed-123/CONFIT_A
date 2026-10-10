"""Single-head & no shared down_revision gate (011 SC-002/003).

Proves the Alembic chain is linear: exactly one head, no two migrations
share the same down_revision, no duplicate revision ids.

Uses ScriptDirectory (same as test_release_schema_parity_gate) to avoid
hardcoded constants — the gate must fail if a second head is introduced,
not pass because a constant was updated.
"""

from pathlib import Path
import re
from collections import Counter

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script_dir():
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "backend" / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_single_alembic_head():
    """SC-002: exactly one head."""
    sd = _script_dir()
    heads = sd.get_heads()
    assert len(heads) == 1, f"migration chain has {len(heads)} heads: {heads} — must be exactly one linear head"


def test_no_duplicate_revision_ids():
    """No two migration files share the same revision id."""
    sd = _script_dir()
    revisions = [rev.revision for rev in sd.walk_revisions()]
    dup = [r for r, c in Counter(revisions).items() if c > 1]
    assert not dup, f"duplicate revision ids found: {dup}"


def test_no_shared_down_revision():
    """SC-003: no two migrations share the same down_revision (linear chain).

    If two files have down_revision == 0034, they branch from the same parent
    and create two heads. The gate must catch that before it reaches prod.
    """
    root = Path(__file__).resolve().parents[2]
    versions_dir = root / "backend" / "alembic" / "versions"
    down_revs = []
    for py in versions_dir.glob("*.py"):
        src = py.read_text()
        # Extract down_revision = "..." or down_revision = None or tuple
        m = re.search(r"down_revision\s*=\s*([^\n]+)", src)
        if not m:
            continue
        val = m.group(1).strip()
        # Handle None, string, tuple
        if val == "None":
            continue
        # Extract quoted strings
        quoted = re.findall(r"['\"]([^'\"]+)['\"]", val)
        for q in quoted:
            down_revs.append((py.name, q))

    # Count down_revision values (ignore None)
    counter = Counter([dr for _, dr in down_revs])
    shared = {dr: cnt for dr, cnt in counter.items() if cnt > 1}
    assert not shared, (
        f"multiple migrations share the same down_revision (branching chain): {shared}. "
        f"Details: {down_revs}. Each down_revision must appear at most once for a linear chain."
    )


def test_chain_is_resolvable_from_base_to_head():
    """All revisions walkable from base to single head without gaps."""
    sd = _script_dir()
    # walk_revisions goes head -> base via down_revision links
    revs = list(sd.walk_revisions())
    assert len(revs) >= 34, f"expected at least 34 revisions, got {len(revs)}"
    # The base should have down_revision None
    bases = [r for r in revs if r.down_revision is None]
    assert len(bases) == 1, f"expected exactly one base (down_revision None), got {len(bases)}: {bases}"
    # Head is the one not used as down_revision by anyone else
    all_down = set()
    for r in revs:
        dr = r.down_revision
        if dr is None:
            continue
        if isinstance(dr, (list, tuple, set)):
            all_down.update(dr)
        else:
            all_down.add(dr)
    heads = [r.revision for r in revs if r.revision not in all_down]
    assert len(heads) == 1, f"expected 1 head via down_revision graph, got {heads}"
