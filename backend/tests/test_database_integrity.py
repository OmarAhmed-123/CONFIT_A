"""Tests for backend/scripts/validate_database.py.

Prove the validator:
  1. Passes clean on a freshly seeded database (baseline invariant).
  2. Detects the specific violations it claims to detect (positive controls).
  3. Detects Group 4-specific violations (invalid processing_status,
     negative wear_count, ai_confidence outside [0,1], duplicate hash).

Every test builds its own throwaway SQLite engine so the assertions cannot
depend on and cannot pollute the shared test DB used by conftest.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine, text

from backend.app.seed_data import seed_database
from backend.scripts.validate_database import validate


def _fresh_seeded_engine():
    """Give each test its own file-scoped SQLite engine with the standard seed.

    The seed does drop_all/create_all internally, so calling it against a
    just-created empty database is safe. Uses ``tempfile`` so no state leaks
    between tests or into the shared confit_test.db used by conftest.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    seed_database(target_engine=engine, force=True)
    return engine, path


class TestValidatorHappyPath:
    def test_freshly_seeded_database_passes(self):
        engine, path = _fresh_seeded_engine()
        try:
            failures = validate(engine)
            assert failures == 0
        finally:
            engine.dispose()
            os.remove(path)


class TestValidatorDetectsGroup4Violations:
    def test_invalid_processing_status_detected(self):
        engine, path = _fresh_seeded_engine()
        try:
            with engine.begin() as conn:
                # Corrupt one wardrobe row with an off-taxonomy status
                conn.execute(text(
                    "UPDATE wardrobe_items SET processing_status='partially_done' "
                    "WHERE id=(SELECT MIN(id) FROM wardrobe_items)"
                ))
            failures = validate(engine)
            assert failures >= 1, "validator should flag invalid processing_status"
        finally:
            engine.dispose()
            os.remove(path)

    def test_negative_wear_count_detected(self):
        engine, path = _fresh_seeded_engine()
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE wardrobe_items SET wear_count=-5 "
                    "WHERE id=(SELECT MIN(id) FROM wardrobe_items)"
                ))
            failures = validate(engine)
            assert failures >= 1, "validator should flag negative wear_count"
        finally:
            engine.dispose()
            os.remove(path)

    def test_ai_confidence_out_of_range_detected(self):
        engine, path = _fresh_seeded_engine()
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE wardrobe_items SET ai_confidence=1.5 "
                    "WHERE id=(SELECT MIN(id) FROM wardrobe_items)"
                ))
            failures = validate(engine)
            assert failures >= 1
        finally:
            engine.dispose()
            os.remove(path)


class TestValidatorDetectsReferentialViolations:
    def test_orphan_cart_item_detected(self):
        """Insert a cart_item with a cart_id that references a deleted cart."""
        engine, path = _fresh_seeded_engine()
        try:
            with engine.begin() as conn:
                # SQLite does not enforce FKs by default in this test path
                # (the app's create_all does not enable PRAGMA foreign_keys),
                # so we can insert an intentional orphan to prove detection.
                conn.execute(text(
                    "INSERT INTO cart_items (cart_id, product_sku_id, quantity, added_at) "
                    "VALUES (99999, 1, 1, CURRENT_TIMESTAMP)"
                ))
            failures = validate(engine)
            assert failures >= 1
        finally:
            engine.dispose()
            os.remove(path)


class TestValidatorDetectsUniqueViolations:
    def test_duplicate_image_hash_detected(self):
        """The DB constraint blocks duplicates via UNIQUE — the validator
        should still detect the case in a database where the constraint was
        never applied (defense-in-depth for older environments)."""
        engine, path = _fresh_seeded_engine()
        try:
            # Drop the unique constraint so we can insert an intentional dup
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE wardrobe_items_new AS "
                    "SELECT * FROM wardrobe_items"
                ))
                conn.execute(text("DROP TABLE wardrobe_items"))
                conn.execute(text("ALTER TABLE wardrobe_items_new RENAME TO wardrobe_items"))
                # Insert two rows with the same (user_id, image_hash)
                conn.execute(text("""
                    INSERT INTO wardrobe_items (user_id, title, category, color_name,
                        color_hex, pattern, brand_name, image_url, ai_tags, occasions,
                        wear_frequency, wear_count, is_favorite, created_at, image_hash,
                        secondary_colors, seasonality, processing_status)
                    VALUES (1, 'dup-A', 'Tops', 'Black', '#000', 'Solid', 'Test',
                        'https://x/1.jpg', '[]', '[]', 'normal', 0, false,
                        CURRENT_TIMESTAMP, 'dup-hash-abc', '[]', 'All-Season', 'ready')
                """))
                conn.execute(text("""
                    INSERT INTO wardrobe_items (user_id, title, category, color_name,
                        color_hex, pattern, brand_name, image_url, ai_tags, occasions,
                        wear_frequency, wear_count, is_favorite, created_at, image_hash,
                        secondary_colors, seasonality, processing_status)
                    VALUES (1, 'dup-B', 'Tops', 'Black', '#000', 'Solid', 'Test',
                        'https://x/2.jpg', '[]', '[]', 'normal', 0, false,
                        CURRENT_TIMESTAMP, 'dup-hash-abc', '[]', 'All-Season', 'ready')
                """))
            failures = validate(engine)
            assert failures >= 1
        finally:
            engine.dispose()
            os.remove(path)


class TestSeedIsIdempotentAndRelational:
    """Cross-check the SEED itself — the validator's happy-path test above
    already proves the produced dataset is relationally clean, so here we
    verify seed-specific invariants."""

    def test_seed_produces_all_required_relationships(self):
        engine, path = _fresh_seeded_engine()
        try:
            with engine.connect() as conn:
                # The seed's designated CONSUMER (shopper@confit.io) must own a
                # complete UserStyleProfile — the app assumes the demo user
                # can log in and immediately hit onboarded flows.
                consumer_profile = conn.execute(text("""
                    SELECT count(*) FROM user_style_profiles usp
                     JOIN users u ON u.id = usp.user_id
                     WHERE u.email = 'shopper@confit.io'
                """)).scalar()
                assert consumer_profile == 1

                # Every seeded outfit has at least one outfit_item
                empty_outfits = conn.execute(text("""
                    SELECT count(*) FROM outfits o
                     WHERE o.id NOT IN (SELECT DISTINCT outfit_id FROM outfit_items)
                """)).scalar()
                assert empty_outfits == 0

                # Financial integrity: for every seeded order, the sum of its
                # order_items subtotals must equal the order's subtotal_amount
                # (within a cent) and the total must equal subtotal - discount
                # + tax + shipping. Regression guard: the seed previously
                # claimed subtotal=384 with items summing to 289, which this
                # test now blocks.
                mismatched_subtotal = conn.execute(text("""
                    SELECT count(*) FROM orders o
                     WHERE ABS(o.subtotal_amount - COALESCE((
                         SELECT SUM(oi.subtotal) FROM order_items oi WHERE oi.order_id=o.id
                     ), 0)) > 0.01
                """)).scalar()
                assert mismatched_subtotal == 0, "subtotal_amount != sum(items.subtotal)"

                mismatched_total = conn.execute(text("""
                    SELECT count(*) FROM orders
                     WHERE ABS(total_amount - (subtotal_amount - discount_amount
                                               + tax_amount + shipping_amount)) > 0.01
                """)).scalar()
                assert mismatched_total == 0, "total_amount != subtotal - discount + tax + shipping"

                # Every product_sku has a valid product
                orphan_skus = conn.execute(text("""
                    SELECT count(*) FROM product_skus s
                     WHERE s.product_id NOT IN (SELECT id FROM products)
                """)).scalar()
                assert orphan_skus == 0
        finally:
            engine.dispose()
            os.remove(path)

    def test_seed_is_idempotent_with_force(self):
        """Two seeds with force=True produce the same set of user emails and
        product titles (idempotent semantics — same inputs, same outputs)."""
        engine, path = _fresh_seeded_engine()
        try:
            with engine.connect() as conn:
                emails_1 = sorted(r[0] for r in conn.execute(text("SELECT email FROM users")))
                products_1 = sorted(r[0] for r in conn.execute(text("SELECT title FROM products")))

            # Second seed against the same engine
            seed_database(target_engine=engine, force=True)

            with engine.connect() as conn:
                emails_2 = sorted(r[0] for r in conn.execute(text("SELECT email FROM users")))
                products_2 = sorted(r[0] for r in conn.execute(text("SELECT title FROM products")))

            assert emails_1 == emails_2
            assert products_1 == products_2
        finally:
            engine.dispose()
            os.remove(path)

    def test_seed_refuses_populated_db_without_force(self, capsys):
        """Safety guard: without ``force``, running seed against a populated
        database refuses (protecting real data)."""
        engine, path = _fresh_seeded_engine()  # already populated by fixture
        try:
            seed_database(target_engine=engine, force=False)
            out = capsys.readouterr().out
            assert "refusing to wipe" in out.lower()
        finally:
            engine.dispose()
            os.remove(path)


class TestSeedRefusesProduction:
    def test_seed_refuses_when_environment_is_production(self, monkeypatch):
        from backend.app.core import config as config_mod
        monkeypatch.setattr(config_mod.settings, "ENVIRONMENT", "production", raising=False)
        with pytest.raises(RuntimeError, match="production"):
            seed_database(force=True)
