#!/usr/bin/env python3
"""Provision (and tear down) disposable brand tenants for portal verification.

WHY THIS EXISTS
---------------
Verifying the B2B portal end to end requires authenticating as a brand manager
and proving BOTH that a tenant sees its own data AND that it cannot see another
tenant's. Doing that with the real seeded accounts (brand@massimodutti.com etc.)
would mean rewriting a real account's password and creating test rows inside a
real brand's tenant. That is exactly the "uncontrolled test data in real
customer tenants" this project forbids.

So this creates self-contained, clearly-labelled, disposable tenants:

    qa-portal-a-<suffix>@confit-portal-qa.example.com   -> brand "QA Portal Tenant A"
    qa-portal-b-<suffix>@confit-portal-qa.example.com   -> brand "QA Portal Tenant B"

Two of them, because a single tenant cannot prove isolation: you need a second
tenant to attempt to reach. They sit under IANA-reserved
`example.com`, which can never route to a real mailbox.

Everything it creates is recorded so `--teardown` can remove exactly those rows
and nothing else. Teardown is keyed on the tenant's own brand_id and user_id, so
it can never cascade into a real brand.

SAFETY
------
  * Password comes from CONFIT_TEST_PASSWORD, never a CLI argument.
  * Refuses to touch any account whose email is not on the test domain.
  * The domain is IANA-reserved `example.com`, which can never receive mail.
  * --teardown deletes only rows owned by the provisioned test brands.
  * Idempotent: re-running reuses the existing tenants rather than duplicating.

Usage:
    CONFIT_TEST_PASSWORD='...' DATABASE_URL=... python3 scripts/provision_portal_test_tenant.py
    DATABASE_URL=... python3 scripts/provision_portal_test_tenant.py --teardown
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.app.core.security import get_password_hash  # noqa: E402

# NOT the RFC 2606 `.invalid` TLD: the application's email validator correctly
# rejects special-use/reserved names, so accounts on it cannot log in and are
# useless for end-to-end verification. `example.com` is IANA-reserved for
# documentation and examples, never resolves to a real mailbox, and passes
# standard email syntax validation.
TEST_DOMAIN = "confit-portal-qa.example.com"
SUFFIX = os.environ.get("CONFIT_TEST_SUFFIX", "v1")
# brand_profiles.brand_name carries a UNIQUE index, so the suffix has to be part
# of the NAME too -- not just the email. Keying idempotency on the email alone
# let a second suffix reach the INSERT and die on
# `duplicate key ... ix_brand_profiles_brand_name`, leaving a half-provisioned
# tenant behind. Every globally-unique column this script writes must be
# suffix-scoped.
TENANTS = [
    (f"qa-portal-a-{SUFFIX}@{TEST_DOMAIN}", f"QA Portal Tenant A ({SUFFIX})"),
    (f"qa-portal-b-{SUFFIX}@{TEST_DOMAIN}", f"QA Portal Tenant B ({SUFFIX})"),
]


def _slug(name: str) -> str:
    """Slugify to the charset the app's own slugs use: lowercase, hyphens only."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _assert_test_account(email: str) -> None:
    """Hard guard: this script must never be able to touch a real account."""
    if not email.endswith("@" + TEST_DOMAIN):
        raise SystemExit(f"REFUSING: {email!r} is not on the disposable test domain "
                         f"@{TEST_DOMAIN}. This script only manages test tenants.")


def provision(conn, password: str) -> list[dict]:
    out = []
    pw_hash = get_password_hash(password)
    for email, brand_name in TENANTS:
        _assert_test_account(email)

        row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).first()
        if row:
            user_id = row[0]
            # Reset the password so the caller always knows the credential.
            conn.execute(text("UPDATE users SET hashed_password = :h WHERE id = :i"),
                         {"h": pw_hash, "i": user_id})
        else:
            # Insert with explicit values for every NOT NULL column that has no
            # server-side default. The ORM defaults are Python-side, so raw SQL
            # does not get them -- `preferred_language` is NOT NULL and its
            # default lives in the model, not the schema.
            user_id = conn.execute(text("""
                INSERT INTO users (email, hashed_password, full_name, role,
                                   preferred_language, is_active, is_verified,
                                   mfa_enabled, created_at, updated_at)
                VALUES (:e, :h, :n, 'BRAND_MANAGER', 'en', TRUE, TRUE,
                        FALSE, NOW(), NOW())
                RETURNING id
            """), {"e": email, "h": pw_hash, "n": brand_name + " (disposable QA account)"}).scalar()

        brow = conn.execute(text("SELECT id FROM brand_profiles WHERE user_id = :u"),
                            {"u": user_id}).first()
        if brow:
            brand_id = brow[0]
        else:
            brand_id = conn.execute(text("""
                INSERT INTO brand_profiles (user_id, brand_name, slug,
                                            description, description_ar, is_verified, created_at)
                VALUES (:u, :n, :slug, 'Disposable tenant for portal verification.',
                        'مستأجر مؤقت للتحقق', TRUE, NOW())
                RETURNING id
            """), {"u": user_id, "n": brand_name,
                   "slug": _slug(brand_name)}).scalar()

        # Give the tenant one product + SKU + store + inventory row so the
        # verification harness can exercise real flows (placements need a real
        # product_id; inventory needs a real store). Without these the tenant
        # is empty and most checks would be vacuous.
        cat_id = conn.execute(text("SELECT id FROM categories ORDER BY id LIMIT 1")).scalar()
        prod_id = conn.execute(text("SELECT id FROM products WHERE brand_id = :b LIMIT 1"),
                               {"b": brand_id}).scalar()
        if not prod_id and cat_id:
            prod_id = conn.execute(text("""
                INSERT INTO products (brand_id, category_id, title, title_ar, slug,
                                      description, description_ar, base_price, currency,
                                      style_tags, occasion_tags, color_family,
                                      thumbnail_url, images, size_chart_json,
                                      is_active, created_at)
                VALUES (:b, :c, :t, :t, :slug, 'QA fixture product', 'منتج اختبار',
                        100.00, 'AED', '[]', '[]', 'Navy',
                        'https://example.com/qa.jpg', '[]', '{}', TRUE, NOW())
                RETURNING id
            """), {"b": brand_id, "c": cat_id, "t": f"{brand_name} QA Product",
                   "slug": f"qa-product-{brand_id}-{SUFFIX}"}).scalar()
        sku_id = None
        if prod_id:
            sku_id = conn.execute(text("SELECT id FROM product_skus WHERE product_id = :p LIMIT 1"),
                                  {"p": prod_id}).scalar()
            if not sku_id:
                sku_id = conn.execute(text("""
                    INSERT INTO product_skus (product_id, brand_id, sku_code, size, color,
                                              stock_level, is_in_stock)
                    VALUES (:p, :b, :code, 'M', 'Navy', 25, TRUE)
                    RETURNING id
                """), {"p": prod_id, "b": brand_id,
                       "code": f"QA-{brand_id}-{SUFFIX}-M"}).scalar()

        store_id = conn.execute(text("SELECT id FROM store_locations WHERE brand_id = :b LIMIT 1"),
                                {"b": brand_id}).scalar()
        if not store_id:
            store_id = conn.execute(text("""
                INSERT INTO store_locations (brand_id, name, name_ar, address, city, country,
                                             latitude, longitude, is_bopis_enabled, created_at)
                VALUES (:b, :n, :n, '1 QA Street', 'Dubai', 'UAE', 25.2, 55.3, TRUE, NOW())
                RETURNING id
            """), {"b": brand_id, "n": f"{brand_name} QA Store"}).scalar()

        if store_id and sku_id:
            exists = conn.execute(text("""SELECT id FROM store_inventories
                                          WHERE store_id = :s AND sku_id = :k"""),
                                  {"s": store_id, "k": sku_id}).scalar()
            if not exists:
                conn.execute(text("""
                    INSERT INTO store_inventories (store_id, sku_id, brand_id, quantity,
                                                   reserved_quantity)
                    VALUES (:s, :k, :b, 12, 2)
                """), {"s": store_id, "k": sku_id, "b": brand_id})

        out.append({"email": email, "user_id": user_id,
                    "brand_id": brand_id, "brand_name": brand_name,
                    "product_id": prod_id, "sku_id": sku_id, "store_id": store_id})
    return out


def teardown(conn) -> int:
    removed = 0
    for email, _ in TENANTS:
        _assert_test_account(email)
        row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).first()
        if not row:
            continue
        user_id = row[0]
        brow = conn.execute(text("SELECT id FROM brand_profiles WHERE user_id = :u"),
                            {"u": user_id}).first()
        if brow:
            bid = brow[0]
            # Delete only rows owned by THIS disposable brand, innermost first.
            conn.execute(text("""
                DELETE FROM store_inventories WHERE store_id IN
                    (SELECT id FROM store_locations WHERE brand_id = :b)"""), {"b": bid})
            conn.execute(text("DELETE FROM store_locations WHERE brand_id = :b"), {"b": bid})
            conn.execute(text("DELETE FROM ad_ledger_entries WHERE brand_id = :b"), {"b": bid})
            conn.execute(text("DELETE FROM sponsored_placements WHERE brand_id = :b"), {"b": bid})
            conn.execute(text("""
                DELETE FROM product_skus WHERE product_id IN
                    (SELECT id FROM products WHERE brand_id = :b)"""), {"b": bid})
            conn.execute(text("DELETE FROM products WHERE brand_id = :b"), {"b": bid})
            conn.execute(text("DELETE FROM brand_profiles WHERE id = :b"), {"b": bid})
        conn.execute(text("DELETE FROM audit_logs WHERE user_id = :u"), {"u": user_id})
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        removed += 1
    return removed


def main() -> int:
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("ALEMBIC_DATABASE_URL")
    if not db_url:
        print("ERROR: set DATABASE_URL first.", file=sys.stderr)
        return 2

    engine = create_engine(db_url)
    with engine.begin() as conn:
        if "--teardown" in flags:
            n = teardown(conn)
            print(f"Removed {n} disposable test tenant(s).")
            return 0

        password = os.environ.get("CONFIT_TEST_PASSWORD")
        if not password:
            print("ERROR: set CONFIT_TEST_PASSWORD (never pass it as an argument).",
                  file=sys.stderr)
            return 2
        result = provision(conn, password)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
