"""Runtime test of migration 0013 against a real database.

Section 20 of the audit brief asks whether migration_audit_log is genuinely
populated or merely created. This builds a throwaway SQLite database holding
the three quarantine cases, runs the real upgrade() function, and inspects the
rows it wrote.

Data-integrity language used deliberately: 0013 preserves ROW COUNT and records
the value it OBSERVED. Where migration 0011 already overwrote an operator's
figure with an invented default (0.5 / 50.0), that original input is
IRRECOVERABLE from this table and requires a backup. 0013 does not and cannot
restore it; it quarantines the row for operator review.
"""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

REPO = Path(__file__).resolve().parents[2]
MIG = REPO / "backend" / "alembic" / "versions" / "0013_migration_audit_and_quarantine.py"


def _load():
    spec = importlib.util.spec_from_file_location("m0013", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def migrated(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path/'m.db'}")
    with engine.begin() as c:
        c.execute(sa.text("""
            create table sponsored_placements(
                id integer primary key, status text,
                bid_amount_per_click float, daily_budget float,
                spent_today float default 0)"""))
        # 1: already "repaired" by 0011 to invented defaults, still active
        c.execute(sa.text("insert into sponsored_placements values (1,'active',0.5,50.0,0)"))
        # 2: structurally invalid bid
        c.execute(sa.text("insert into sponsored_placements values (2,'active',-5,20.0,0)"))
        # 3: overspent
        c.execute(sa.text("insert into sponsored_placements values (3,'active',5,20.0,999)"))
        # 4: perfectly valid, must be left alone
        c.execute(sa.text("insert into sponsored_placements values (4,'active',2,20.0,1)"))

    mod = _load()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import alembic

    with engine.begin() as conn:
        alembic.op._proxy = Operations(MigrationContext.configure(conn))
        mod.upgrade()
    return engine


def _rows(engine, q):
    with engine.connect() as c:
        return [tuple(r) for r in c.execute(sa.text(q))]


class TestMigration0013QuarantineIsAudited:
    def test_all_invalid_placements_are_quarantined(self, migrated):
        status = dict(_rows(migrated, "select id, status from sponsored_placements"))
        assert status[1] == "paused"
        assert status[2] == "paused"
        assert status[3] == "paused"

    def test_valid_placement_is_not_touched(self, migrated):
        status = dict(_rows(migrated, "select id, status from sponsored_placements"))
        assert status[4] == "active", "0013 must not quarantine valid placements"

    def test_row_count_is_preserved(self, migrated):
        """Rows are paused, never deleted."""
        n = _rows(migrated, "select count(*) from sponsored_placements")[0][0]
        assert n == 4

    def test_every_quarantined_row_has_an_audit_record(self, migrated):
        """The regression: the invalid_checks loop used to pause without auditing."""
        paused = {r[0] for r in _rows(
            migrated, "select id from sponsored_placements where status='paused'")}
        audited = {r[0] for r in _rows(
            migrated, "select distinct row_id from migration_audit_log")}
        assert paused - audited == set(), (
            f"paused without any audit row: {sorted(paused - audited)}")

    def test_audit_records_the_offending_value_and_action(self, migrated):
        rows = _rows(migrated,
                     "select row_id, field_name, original_value, remediated_value, action "
                     "from migration_audit_log order by row_id")
        by_id = {r[0]: r for r in rows}

        # structurally invalid bid: the offending number is captured
        assert by_id[2][1] == "bid_amount_per_click"
        assert float(by_id[2][2]) == -5.0
        # overspend: captured on the offending field
        assert by_id[3][1] == "spent_today"
        assert float(by_id[3][2]) == 999.0

        for r in rows:
            assert r[3] == "paused"
            assert r[4] == "quarantine"

    def test_audit_does_not_claim_to_restore_lost_values(self, migrated):
        """Row 1's operator-entered bid was overwritten by 0011 and is gone.

        0013 must record only what it observed (the invented 0.5/50.0 default or
        the status transition) and must not present a recovered original.
        """
        row = [r for r in _rows(
            migrated,
            "select row_id, field_name, original_value, reason from migration_audit_log")
            if r[0] == 1][0]
        # it logs the status transition, not a fabricated pre-0011 bid
        assert row[1] == "status"
        assert row[2] == "active"
        # bid on disk is still the invented default: not restored, just quarantined
        bid = _rows(migrated,
                    "select bid_amount_per_click from sponsored_placements where id=1")[0][0]
        assert bid == 0.5
