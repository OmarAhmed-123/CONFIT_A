# Orphaned media objects — inventory and retention proposal

**Status:** PROPOSED. Nothing has been deleted. Deletion requires an explicit
retention decision from the owner (see §5).
**Measured:** 2026-10-20, read-only against bucket `confit-a-media` and the
production `product_images` registry.

## 1. What an "orphan" is here

A media object is orphaned when no `product_images` row carries its key. Because
`GET /api/v1/media/{key}` serves a key **only if a row carries it**, an orphan is
unreachable through the application: it is not a broken link, it is an object
nobody can request.

## 2. Inventory — 20 objects, 3.01 MB

All 20 belong to products 9 and 18 and were written by the 2026-10-20 ladder
repair, which re-rendered both products and then re-published them under
date-suffixed keys.

| Product | Ratios | Formats | Keys | Bytes | Written |
|---|---|---|---|---|---|
| 9 — clutch | 4x5, 1x1, 3x2, 16x9, master | jpeg, webp | `products/9/9-<ratio>.<ext>` | 1,481,645 | 2026-10-20 20:32 |
| 18 — overshirt | 4x5, 1x1, 3x2, 16x9, master | jpeg, webp | `products/18/18-<ratio>.<ext>` | 1,455,860 | 2026-10-20 20:32 |

Full key/size/dimension list: `orphan_objects.json`.

## 3. The finding that changes the risk

**All 20 are byte-identical to the live object at the corresponding
`-20261020` key** — verified by SHA-256, 20 of 20, 0 differences.

So they are not stray files, drafts or foreign content. They are an exact second
copy of what the storefront serves today. Deleting them cannot change a single
pixel a customer sees.

## 4. Why they exist

Media responses carry `Cache-Control: public, max-age=31536000, s-maxage=31536000, immutable`.
A corrected object published at an existing key is therefore invisible: the CDN
keeps answering with the old bytes, and the registry's new checksum describes
bytes no browser can obtain. The repair published under new keys and repointed
the rows — which leaves the previous keys in place as unreferenced copies.

They were deliberately **not** deleted at the time: deleting production objects
to tidy a bucket, without an approved retention policy, is not a maintenance
task.

## 5. Recommendation

| Action | Objects | Rationale |
|---|---|---|
| **Retain** (recommended, and the default) | all 20 | 3.01 MB. They are the rollback path for the 2026-10-20 repair: restoring the previous registry snapshot names these keys. |
| Delete | none yet | Deletion saves 3 MB and buys no correctness. It also does **not** purge the CDN entries that cache these URLs — those live for one year and can only be cleared with project-purge permission this token does not have. |

**Deletion precondition, if it is ever wanted:** (1) the 30-day rollback window
has passed, (2) a manifest with SHA-256 per object is archived, (3) `--verify`
reports `incomplete_ladder_count: 0` at that time, and (4) the CDN has been
purged or the year has elapsed — otherwise deleting the object changes nothing
observable while removing the ability to restore.

**Method when approved** (auditable, reversible-by-manifest):

```bash
# 1. record, don't delete
python - <<'PY'
# list unreferenced keys, hash each, write manifest.json
PY
# 2. delete only the keys named in the manifest, then re-run:
python -m backend.scripts.verify_product_media --skip-http
```

## 6. What is *not* in this set — and matters more

The **wrong** stock photographs (a coral designer handbag, a man in a shirt and
tie) that had been sitting at these exact keys since 2026-10-07 were **overwritten
by the repair**, because `put_object` at an existing key replaces it. They are no
longer in the bucket.

They are preserved outside it, in `/home/user/backups/objects_pre_repair/`
(12 files + `manifest.json`), which is where the evidence for the original defect
lives. That directory is a local operations artifact, not part of the repository
or of any deployment — it should be archived wherever operational evidence is
kept, because the bucket no longer holds it.

## 7. Unrelated bucket content

`products/1…8,19,20` hold 100 referenced objects, all registered and verified.
No other prefixes were inspected; this inventory is scoped to the two repaired
products and makes no claim about the rest of the bucket.
