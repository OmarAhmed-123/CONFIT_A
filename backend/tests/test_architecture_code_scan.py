"""Architecture test — §21 / AT-07 (static half): fixture-ID isolation scan.

The dynamic-phase master prompt (§21, non-negotiable) requires:

    "Scan production code to prove that benchmark fixture IDs never enter
     production decision paths. The result of that scan must be zero."

These tests scan ALL production decision code (backend app, alembic
migrations, frontend sources) for any reference to benchmark fixture
identifiers — person fixture IDs (p001..p030), garment fixture IDs
(g001..g024, g110..g129 text/OCR series), the sleeve-transfer series
(S_g010/S_g012/...), clean-swap controls (KB04/KB12), or the fixture
directory paths. Only the isolated evaluation modules under
``evaluation/`` may name fixture IDs.

The scan is a hard gate: any hit is a FAIL.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO.parent / "CONFIT_A_frontend"

# (name, pattern) — each pattern must have ZERO matches in production code.
ID_PATTERNS = [
    ("person fixture ids p001-p030", re.compile(r"\bp0(?:0[1-9]|[12]\d|30)\b")),
    ("garment fixture ids g001-g024", re.compile(r"\bg0(?:0[1-9]|1\d|2[0-4])\b")),
    ("text/OCR fixture ids g110-g129", re.compile(r"\bg1[12]\d\b")),
    ("sleeve-transfer series S_g0xx", re.compile(r"\bS_g0\d{2}\b")),
    ("clean-swap controls KB0x", re.compile(r"\bKB0\d\b")),
    ("fixture persons directory", re.compile(r"fixtures/persons")),
    ("fixture garments directory", re.compile(r"fixtures/garments")),
    ("evaluation fixtures root", re.compile(r"evaluation/fixtures")),
]


def _production_files():
    roots = [
        REPO / "backend" / "app",
        REPO / "backend" / "alembic",
        FRONTEND / "src" if (FRONTEND / "src").exists() else FRONTEND,
    ]
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".css", ".sql", ".ini", ".yml", ".yaml"}:
                yield p


def test_production_source_trees_exist():
    """Sanity: the scan must actually have production code to scan."""
    assert (REPO / "backend" / "app").is_dir(), "backend/app missing — scan is meaningless"
    n = sum(1 for _ in _production_files())
    assert n > 50, f"only {n} production files found — scan is meaningless"


@pytest.mark.parametrize("name,pat", ID_PATTERNS, ids=[n for n, _ in ID_PATTERNS])
def test_no_fixture_ids_in_production_decision_paths(name, pat):
    """§21: fixture/benchmark IDs must never enter production decision paths.

    Expected: ZERO matches anywhere in production code.
    """
    hits = []
    for f in _production_files():
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for m in pat.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{f.relative_to(REPO.parent)}:{line}")
    assert not hits, (
        f"§21 VIOLATION — fixture ID pattern {name!r} found in production code "
        f"({len(hits)} hit(s)): {hits[:10]}{'...' if len(hits) > 10 else ''}"
    )


def test_no_hardcoded_sleeve_exceptions_by_fixture_id():
    """AT-19 (static half): no ``if garment_id == 'g010'``-class exceptions.

    The sleeve/quality logic must be generic (metadata + geometry + pose +
    output). A production code path that special-cases a benchmark garment by
    ID is a direct violation — this is the exact anti-pattern that produced
    the 17/20 blind PASS in Phase 0.5.
    """
    suspect = re.compile(
        r"(?:sleeve|verify|gate|quality)[^\n]{0,120}?(?:g0\d{2}|p0\d{2})|"
        r"(?:g0\d{2}|p0\d{2})[^\n]{0,120}?(?:sleeve|verify|gate|quality)",
        re.IGNORECASE,
    )
    hits = []
    for f in _production_files():
        if f.suffix != ".py":
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for m in suspect.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{f.relative_to(REPO.parent)}:{line}: {m.group(0)[:80]!r}")
    assert not hits, (
        "AT-19 VIOLATION — production code couples sleeve/quality logic to "
        f"fixture IDs: {hits[:10]}"
    )
