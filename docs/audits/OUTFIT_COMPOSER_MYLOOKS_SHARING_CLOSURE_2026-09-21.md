# Closure report — Outfit Composer, My Looks & public sharing

**Project:** CONFIT_A
**Feature area:** `/builder`, `/outfits`, `/outfits/:id`, `/my-looks`, `/looks/:token`
**Audit answered:** "Outfit Composer وMy Looks والمشاركة العامة" (2026-09-21)
**Branch:** `feat/outfit-composer-mylooks-sharing`
**Status:** implemented and test-verified in CI; **production deployment blocked on one migration step** (see §6)

> This report is for improvement and learning, not blame. Nothing below is
> described as verified unless the evidence for it is named and reproducible.
> Where something is *not* proven, it is stated plainly as not proven.

---

## 1. What the audit actually found

The original audit was careful and correct: it verified that the routes and
controllers **existed**, and explicitly refused to claim that saving, editing
or sharing **worked**, because it had never created an outfit or a token in
production. Reading `GET /outfits` and receiving `200` with an empty list
proves reachability and nothing more.

Our own code review confirmed the audit's caution was justified. The gaps were
real, and there were more of them than the audit could see from the outside.

## 2. Gaps found, and what was wrong underneath

| # | Gap | Why it mattered |
|---|-----|-----------------|
| G1 | `share_token` had **no lifecycle**: no expiry, no revocation, no usage record | Once a link was minted it was permanent and unrevocable. A user who shared a look with one person could never take it back. This is an unbounded, unauthenticated read surface. |
| G2 | `save_outfit` accepted **any** SKU set | Two pairs of shoes, the same blazer in two sizes, a duplicated SKU, or a 60-item payload all persisted as a "look". The total price silently double-counted duplicates. |
| G3 | Saved looks were effectively **immutable** | `PATCH` only touched title/occasion/description. There was no endpoint to change a saved look's *contents* at all, so "reopen and edit" was impossible. |
| G4 | `/outfits/:id` mounted an **empty builder** | "Edit this look" therefore created a silent **duplicate** and never touched the original. |
| G5 | `/my-looks` rendered the **wardrobe** | Saved outfits had no home in the product. |
| G6 | `sort_order` stored the client's **arrival index** | The canvas rendered "shoes, blazer, shirt" if that was the order the client happened to post. Layers had no semantics anywhere. |
| G7 | No way to **see or revoke** a published link from the UI | Exactly the "Export Look Card implies a published link" concern the audit raised. |
| G8 | A rejected combination gave **no reason** | The audit asked for this explicitly. |
| G9 | `/public/looks/{token}` was **unthrottled** | The token is the only credential on that endpoint. |

## 3. What was implemented

### Data & migration
`backend/alembic/versions/0018_outfit_share_lifecycle.py` adds
`share_expires_at`, `share_revoked_at`, `share_view_count`, `updated_at` to
`outfits`. Additive-only, idempotent, clean downgrade, with `updated_at`
backfilled from `created_at` so "last edited" is never a lie for old rows.
The schema gate (`core/schema_gate.py`) now knows these columns, so a drifted
database cannot silently serve unrevocable links.

### Domain layer (Design Patterns / DRY / architecture)
`backend/app/services/styling/composition_policy.py` is a new **pure,
I/O-free policy module** — the single source of truth for what a valid outfit
is, what its layer order is, and how many items each slot holds. It is imported
by the save path, the edit path, the dry-run preview and the tests, so there is
exactly one implementation of "is this outfit valid" in the codebase. It builds
*on top of* the existing `styling/ontology` classification rather than
duplicating it. Violations are returned as structured objects
(`code` + message + offending positions), not booleans — which is what makes
G8 fixable in the UI.

### Service & API
- `POST /outfits` now validates before persisting and raises an explainable 422.
- `PUT /outfits/{id}/items` — **new**: atomic whole-set replacement (G3).
  Whole-set rather than per-item because the policy validates a *set*; it is
  also idempotent under retry.
- `POST /outfits/composition/preview` — **new**: dry-run the same policy.
- `POST /outfits/{id}/share` — now returns real expiry + active flag, is
  idempotent, and accepts `rotate` to invalidate a leaked link.
- `GET /outfits/{id}/share` — **new**: owner-facing truth (active?, expiry,
  real view count).
- `DELETE /outfits/{id}/share` — **new**: revocation (G1).
- `GET /public/looks/{token}` — resolves only when *minted AND not revoked AND
  not expired*; all three failure modes return an indistinguishable 404 so a
  probe cannot learn that a link once existed. Now rate limited.

Every outfit verb remains ownership-checked, returning 404 (not 403) to a
non-owner so outfit existence is not leaked.

### Frontend
- `MyLooksView` + `useMyLooksViewModel` (G5): the real saved-look collection,
  with rename, delete, and a share panel showing the **server's** state —
  active?, real expiry, real view count — plus copy / open / rotate / revoke.
- The builder hydrates from a saved look and updates it in place (G4),
  restoring the exact stored SKU rather than "some in-stock SKU".
- The canvas calls the preview endpoint and gates Save on the server verdict,
  showing the violation message and the offending slot (G8).

Truthfulness rules applied throughout: a look is shown as *shared* only when
the server reports a live token; a **failed** revoke never optimistically
pretends the link is gone; a partially-rehydrated canvas says so.

## 4. Evidence

| Evidence | Where |
|---|---|
| 19 backend tests: save → My Looks → edit → reopen → mint → **anonymous open** → revoke → 404 → expiry → re-share yields a different token; plus PII-leak and cross-user checks | `backend/tests/test_outfit_composer_lifecycle.py` |
| 15 frontend tests, incl. an explicit regression that editing does **not** create a duplicate look, and that a failed revoke does not fake success | `useMyLooksViewModel.test.tsx`, `useOutfitBuilderEditMode.test.tsx` |
| Migration `0018` applied and rolled back on **real PostgreSQL 17** | CI job `postgres migration chain + schema gate` — green |
| Frontend typecheck, unit suite (125/125) and production build | CI job `frontend` — green |
| No new backend failures vs. `main` | Full-suite diff run before/after on the same machine |

**Known environment caveat, stated honestly:** 36 backend tests fail in this
sandbox (VTON / AI / payment modules) both **before and after** these changes.
They are caused by optional dependencies missing locally, are unrelated to this
feature area, and are green in CI where those deps are installed.

## 5. What is still NOT proven

- Nothing here has been exercised against the **live production database**.
  Every claim above rests on CI and local runs.
- Expiry is proven by backdating a row, not by waiting 30 real days.
- Load/abuse behaviour of the public endpoint beyond the rate limit is untested.
- The PNG share-card export path was not changed and was not re-verified.

## 6. Required operational step before this reaches production

The release gate **correctly blocked** the merge with:

```
RELEASE GATE: BLOCK
  commit requires : 0018_outfit_share_lifecycle
  production has  : 0017_audit_before_after_request_id
```

This is the gate doing its job — merging first would deploy code the production
schema cannot serve. The migration must be applied **before** merge:

```bash
ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini upgrade head
ALEMBIC_DATABASE_URL='<owner DSN>' PYTHONPATH=. alembic -c backend/alembic.ini current   # expect 0018
```

The gate then passes on its own. The Neon credentials available to this work
were rejected by the server (`password authentication failed for
'neondb_owner'`), so **this step has not been performed** and is handed over
rather than claimed as done.
