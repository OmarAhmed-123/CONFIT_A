# SKU identity — internal code vs. customer-facing code

**Status:** PROPOSAL ONLY. No migration is authorised, none has been run, and
no column has been renamed.
**Prepared:** 2026-10-20, from the production schema and every read site in
`app/`.

## 1. The decision this document asks for

`product_skus.sku_code` currently does two jobs at once:

1. **the internal identity** of a variant — unique, immutable, referenced by
   order lines, cart items, inventory rows, reservations and reports;
2. **the string a brand owner types and sees** — searched, rendered in error
   messages, exported in CSVs, printed in the pick list.

Those two jobs pull in opposite directions. An internal key must never change
and belongs to the platform. A display code is branding: it should follow the
brand, be readable by a human, and be free to differ from whatever the row was
first created with. Today they are the same column, so neither can change
without the other.

## 2. What is true today (verified, not assumed)

| Property | Value |
|---|---|
| Column | `product_skus.sku_code VARCHAR(100) NOT NULL UNIQUE`, index `ix_product_skus_sku_code` |
| Production rows | 28 legacy codes with the prefixes `MD-`, `REISS-`, `COS-`, `ARK-` |
| References by `sku_id` | `order_items` 21, `cart_items` 34, `outfit_items` 6, `inventory_reservations` 29, `store_inventories` 46 — **100 %**, no declared FK, no row references a code |
| Read sites in application code | 24 in `brand_catalog_service` (import/export/generation), 10 in `commerce_service` (availability errors, order lines), 8 in `admin_catalog_service`, 2 in `search_service`, 1 in `business_intelligence_service`, plus schemas |
| Public exposure | **Closed** on 2026-10-20 (`f1e50c9`): the public PDP payload reports `sku_code: null`; tenant surfaces still carry it. `test_public_sku_code_withheld.py` pins it |
| Retired prefixes | The brands were renamed (Massimo Dutti → Atelier Sable, COS → Casa Lumen, Reiss → Riven Studio, Arket → Nordhaus) but the codes kept their old prefixes |

The last row is the concrete symptom: a customer-facing identifier that says
`REISS-` on a product sold by Riven Studio.

## 3. Why "just rename them" is wrong

* The codes may be on physical labels, in supplier systems and in the owners'
  own spreadsheets. Rewriting them silently breaks the one thing they are
  actually for — matching a garment to a row.
* Nothing references the code internally (100 % of references are by `sku_id`),
  so a rename buys **no** integrity. It only changes strings.
* A rename is irreversible without a mapping table, and would need to be applied
  to historical orders to stay consistent — i.e. it would rewrite history to
  make today's branding tidy.

## 4. Proposed target model

Keep identity, add presentation. One column added, nothing renamed:

| Field | Role | Rules |
|---|---|---|
| `sku_code` (existing) | **Internal identity.** Immutable. | `NOT NULL UNIQUE`, unchanged. Never shown to a customer. Never regenerated once assigned. |
| `display_code` (new, nullable) | **What a human sees.** | Nullable. Unique per brand when present: `UNIQUE (brand_id, display_code)`. Editable. May be blank, in which case surfaces fall back to `sku_code`. |

Why nullable rather than backfilled: every one of the 28 legacy rows would need
an invented value, and inventing a display code for someone else's stock is the
same class of error as renaming it. Blank means "the brand has not chosen one",
which is true, and the fallback keeps every surface rendering something.

Why `UNIQUE (brand_id, display_code)` rather than globally unique: a display code
is branding, and two brands may legitimately both sell a "BLACK-M". The internal
`sku_code` keeps the global guarantee.

### Serialization rule

| Surface | `sku_code` | `display_code` |
|---|---|---|
| Public catalogue (`/catalog/**`) | absent / `null` (already enforced) | present when set, else absent |
| Brand owner / partner | present | present |
| Admin | present | present |
| Order lines, pick lists, exports | present | present when set |

One rule, applied at the serializer: *internal codes never cross the public
boundary; display codes always may.* The existing withholding is therefore a
special case of the new rule rather than a patch to be undone.

## 5. Migration and rollout (only if approved)

1. **Migration**: `ALTER TABLE product_skus ADD COLUMN display_code VARCHAR(64) NULL;`
   plus `CREATE UNIQUE INDEX ux_product_skus_brand_display ON product_skus (brand_id, display_code) WHERE display_code IS NOT NULL;`
   No backfill. Nullable, so it is backward compatible and reversible by
   `DROP COLUMN` with no data loss.
2. **Serializers**: add `display_code` to the tenant and admin schemas; keep the
   public payload's `sku_code: null` contract untouched.
3. **Import/export**: accept an optional `display_code` column; a re-upload that
   omits it does not clear an existing value (same rule as `gender`).
4. **Search**: match on both, rank a `display_code` hit equal to a `sku_code`
   hit; the response must not disclose which is which to a public caller.
5. **Validation**: display codes are customer-visible, so they need the
   prohibited-content check the title already has.
6. **Rollback**: drop the column. Nothing depends on it for identity.

**Effort:** one migration, ~6 files, plus tests. **Risk:** low (additive,
nullable, unused until surfaces opt in). **Blocked on:** an owner decision on
whether brands want to author display codes at all, and who may see them.

## 6. What was done in this release, and what was not

* Done: the public leak is closed and pinned by tests; tenant workflows keep the
  code they need.
* Not done, deliberately: no rename, no new column, no migration, no backfill.
  The 28 legacy codes and every historical reference are exactly as they were.
