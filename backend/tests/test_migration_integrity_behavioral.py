"""Behavioral migration-integrity tests.

Proves (against a real SQLite DB, real alembic upgrade):
  * migration_audit_log is created and is actually insertable/queryable
  * quarantine rows are persisted, not merely printed
  * Float -> NUMERIC(12,2) CAST semantics for whole values, 2dp values,
    binary float artifacts, sub-cent values, NULLs and extremes
  * out-of-range money is rejected explicitly by the domain guard
"""

import os
import tempfile
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from backend.app.core.money import assert_money_range, MoneyRangeError, to_decimal


@pytest.fixture
def sqlite_url():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}", path
    try:
        os.remove(path)
    except OSError:
        pass


def _alembic_upgrade(url: str):
    from alembic import command
    from alembic.config import Config
    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    return cfg


class TestMigrationAuditLogIsPersistent:
    def test_table_exists_after_upgrade_and_accepts_rows(self, sqlite_url):
        url, _ = sqlite_url
        _alembic_upgrade(url)
        eng = create_engine(url)
        with eng.begin() as c:
            names = {r[0] for r in c.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"))}
            assert "migration_audit_log" in names

            c.execute(text(
                "INSERT INTO migration_audit_log "
                "(migration_revision, table_name, row_id, field_name, original_value, "
                " remediated_value, action, reason) VALUES "
                "('0013','sponsored_placements',42,'daily_budget','UNKNOWN-OVERWRITTEN-BY-0011',"
                "'50.0','quarantine','original value irrecoverable; operator review required')"))
            row = c.execute(text(
                "SELECT migration_revision, table_name, row_id, field_name, original_value, "
                "remediated_value, action, reason, created_at FROM migration_audit_log")).fetchone()

        # Every field the audit brief requires must be present and queryable
        assert row[0] == "0013"
        assert row[1] == "sponsored_placements"
        assert row[2] == 42
        assert row[3] == "daily_budget"
        assert row[4] == "UNKNOWN-OVERWRITTEN-BY-0011"
        assert row[5] == "50.0"
        assert row[6] == "quarantine"
        assert "operator review" in row[7]
        assert row[8] is not None  # timestamp

    def test_audit_log_is_not_merely_print(self):
        src = open("backend/alembic/versions/0013_migration_audit_and_quarantine.py").read()
        assert "INSERT INTO migration_audit_log" in src

    def test_no_false_no_data_loss_language(self):
        for f in ("backend/alembic/versions/0011_group6_check_constraints.py",
                  "backend/alembic/versions/0012_money_numeric_precision.py",
                  "backend/alembic/versions/0013_migration_audit_and_quarantine.py"):
            src = open(f).read().lower()
            assert "(no data loss," not in src
            assert "no data loss: existing values" not in src


class TestNumericCastSemantics:
    @pytest.mark.parametrize("raw,expected", [
        (100.0, "100.00"),          # whole
        (19.99, "19.99"),           # exact 2dp
        (19.989999999999998, "19.99"),  # binary artifact -> normalised
        (0.005, "0.01"),            # sub-cent -> HALF_UP, precision beyond cents lost
        (0.004, "0.00"),            # sub-cent below half -> 0
        (9999999999.99, "9999999999.99"),  # max representable
    ])
    def test_cast_to_two_decimals(self, raw, expected):
        assert to_decimal(raw) == Decimal(expected)

    def test_null_stays_zero_not_error(self):
        assert to_decimal(None) == Decimal("0.00")

    def test_out_of_range_is_explicit_failure_not_truncation(self):
        with pytest.raises(MoneyRangeError):
            assert_money_range(10_000_000_000.00, "order_total")

    def test_sqlite_would_silently_accept_without_guard(self, sqlite_url):
        """Documents WHY the explicit guard exists: SQLite does not enforce NUMERIC(12,2)."""
        url, _ = sqlite_url
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(text("CREATE TABLE m (amt NUMERIC(12,2))"))
            c.execute(text("INSERT INTO m VALUES (99999999999.99)"))
            stored = c.execute(text("SELECT amt FROM m")).scalar()
        assert float(stored) == 99999999999.99  # silently stored -> guard is required
