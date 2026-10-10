"""Money column preservation gate (011 SC-005, DB-19).

Ensures no migration converts money columns away from Numeric(12,2).
"""

from pathlib import Path
import re

def test_money_columns_remain_numeric_12_2():
    """SC-005: grep/structural check — 0 money columns converted away from Numeric(12,2)."""
    repo_root = Path(__file__).resolve().parents[2]
    models_dir = repo_root / "backend" / "app" / "models"

    # Money columns are defined as Numeric(12,2) in models.
    # Check that models still use Numeric(12,2) for money fields, not Float.
    money_fields = [
        "base_price",
        "price_override",
        "total_amount",
        "subtotal",
        "discount",
        "tax_amount",
        "shipping_amount",
        "unit_price",
        "amount",
        "refund",
    ]

    # Scan all model files for Float usage on money-named columns (heuristic)
    float_money_violations = []
    for py in models_dir.glob("*.py"):
        src = py.read_text()
        # Look for Column(Float) with money-like names nearby
        # Simple heuristic: if a money keyword appears within 100 chars of Float
        # This is intentionally strict to catch regressions
        for match in re.finditer(r"Column\s*\(\s*Float", src):
            start = max(0, match.start() - 200)
            end = min(len(src), match.end() + 200)
            snippet = src[start:end].lower()
            for keyword in money_fields:
                if keyword.lower() in snippet:
                    float_money_violations.append(f"{py.name}: Float near {keyword} at {match.start()} -> {snippet[:200]}")
                    break

    assert not float_money_violations, (
        f"Money columns must remain Numeric(12,2), not Float (DB-19). Violations:\n"
        + "\n".join(float_money_violations[:20])
    )

    # Also check that Numeric(12,2) appears in models (positive check)
    numeric_count = 0
    for py in models_dir.glob("*.py"):
        src = py.read_text()
        numeric_count += src.count("Numeric(12, 2)")
        numeric_count += src.count("Numeric(12,2)")

    assert numeric_count >= 10, f"Expected at least 10 Numeric(12,2) usages in models, found {numeric_count} — money preservation may have regressed"

def test_migration_files_do_not_convert_money_to_float():
    """Ensure no migration file downgrades Numeric to Float for money."""
    repo_root = Path(__file__).resolve().parents[2]
    versions_dir = repo_root / "backend" / "alembic" / "versions"

    violations = []
    for py in versions_dir.glob("*.py"):
        src = py.read_text()
        # Look for patterns where money columns are altered to Float in downgrade or upgrade
        # This is a safety net: migrations 0012 does Float->Numeric, which is allowed.
        # What is NOT allowed is Numeric->Float for money.
        # We check for explicit alter_column to Float with money names
        if "Numeric" in src and "Float" in src:
            # If file is 0012, it's the known conversion TO Numeric, skip
            if "0012_money_numeric_precision" in py.name:
                continue
            # Check if any money field is altered TO Float (downgrade is ok for 0012, but not for others)
            # For other migrations, altering money to Float is a violation
            # We look for money keywords + Float in same file as potential risk
            # Only flag if upgrade() contains Float for money
            # Simple: if upgrade function contains Float and money keyword, warn
            upgrade_section = src.split("def upgrade")[1].split("def downgrade")[0] if "def upgrade" in src and "def downgrade" in src else src
            for keyword in ["total_amount", "subtotal", "discount_amount", "tax_amount", "shipping_amount", "unit_price", "base_price"]:
                if keyword in upgrade_section.lower() and "Float" in upgrade_section:
                    # Allow if it's part of a check or comment, not alter
                    if f'"{keyword}"' in upgrade_section or f"'{keyword}'" in upgrade_section:
                        violations.append(f"{py.name}: potential money->Float in upgrade for {keyword}")

    # This is informational, not hard fail, because some migrations legitimately touch money in downgrade
    # But we assert no violations in upgrade path for non-0012 migrations
    assert not violations, f"Money columns converted away from Numeric(12,2) in upgrade path: {violations}"
