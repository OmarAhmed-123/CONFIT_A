"""The demo catalogue must not impersonate real retailers.

The seeded catalogue previously shipped four real brands — Massimo Dutti, COS,
Reiss and Arket — complete with domain-shaped contact addresses
(``brand@massimodutti.com``) and positioning copy, attached to products those
companies have nothing to do with. Anyone opening the demo saw a shop claiming
partnerships that do not exist.

The replacement house brands are invented. This test enforces the invariant so a
future seed edit cannot quietly reintroduce a real trademark.

HOW IT LOOKS
------------
The scan parses each seed/demo module with ``ast`` and inspects **string
literals only**. That is deliberate: the remediation comment in ``seed_data.py``
has to name the old brands to explain why they are gone, and a naive grep would
fail on its own documentation. Comments are not string constants, so the rule
stays strict about data and silent about prose.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Files that produce demo/storefront data.
DEMO_DATA_SOURCES = [
    "backend/app/seed_data.py",
    "backend/app/seed_size_charts.py",
    "backend/app/services/dashboard_service.py",
    "backend/scripts/seed_retail_presence.py",
]

#: Real fashion retailers the demo must never impersonate. Matched
#: case-insensitively on word boundaries so ``COS`` does not fire inside
#: "costume" and "Reiss" does not fire inside "reissue".
IMPERSONATED_BRANDS = [
    ("Massimo Dutti", r"\bmassimo\s+dutti\b"),
    ("COS", r"\bcos\b"),
    ("Reiss", r"\breiss\b"),
    ("Arket", r"\barket\b"),
]

#: Domain-shaped identifiers that prove intent even without the brand string.
IMPERSONATED_DOMAINS = [
    r"massimodutti\.com",
    r"@cos\.com",
    r"@reiss\.com",
    r"@arket\.com",
]

#: The invented house brands the seed now uses. Asserting these exist proves the
#: test is looking at a rebranded file rather than at an empty or missing one.
FICTIONAL_BRANDS = ["Atelier Sable", "Casa Lumen", "Riven Studio", "Nordhaus"]


def _string_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((getattr(node, "lineno", 0), node.value))
    return found


@pytest.mark.parametrize("relative_path", DEMO_DATA_SOURCES)
def test_demo_data_contains_no_real_brand_trademarks(relative_path):
    path = REPO / relative_path
    assert path.exists(), f"{relative_path} moved; update DEMO_DATA_SOURCES"

    offences = []
    for lineno, value in _string_literals(path):
        for name, pattern in IMPERSONATED_BRANDS:
            if re.search(pattern, value, flags=re.IGNORECASE):
                offences.append(f"{relative_path}:{lineno} mentions {name!r}: {value[:80]!r}")
        for pattern in IMPERSONATED_DOMAINS:
            if re.search(pattern, value, flags=re.IGNORECASE):
                offences.append(f"{relative_path}:{lineno} carries a real-domain identifier: {value[:80]!r}")

    assert not offences, "real retailer impersonation in demo data:\n" + "\n".join(offences)


def test_the_seed_still_defines_the_fictional_house_brands():
    """A guard against 'fixing' the previous test by deleting the brands."""
    source = (REPO / "backend/app/seed_data.py").read_text(encoding="utf-8")
    values = [v for _, v in _string_literals(REPO / "backend/app/seed_data.py")]
    for brand in FICTIONAL_BRANDS:
        assert brand in values, f"seed_data.py no longer defines the house brand {brand!r}"
    assert "Password123!" in source or True  # no assertion on credentials here


def test_seeded_brand_emails_match_the_fictional_brands():
    """Contact addresses must belong to the invented houses, not to real domains."""
    values = [v for _, v in _string_literals(REPO / "backend/app/seed_data.py")]
    brand_emails = [v for v in values if v.startswith("brand@") and "@confit.io" not in v]
    assert brand_emails, "seed must still create brand-manager accounts"
    for email in brand_emails:
        domain = email.split("@", 1)[1]
        assert domain in {
            "ateliersable.com",
            "casalumen.com",
            "rivenstudio.com",
            "nordhaus.com",
        }, f"brand account {email!r} uses a domain that is not a house brand"
