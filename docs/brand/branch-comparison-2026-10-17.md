# Branch comparison — UI/UX audit and Logo #3 consistency (2026-10-17)

Status vocabulary follows `.specify/memory/constitution.md`. Every row below was
established from `git log`, `git cherry`, `git diff` and the GitHub REST API
(PR list, check-runs, branch protection) on 2026-10-17, not from branch names.
No branch was deleted, rebased or force-pushed. A throwaway local branch
(`probe`) was used for merge/cherry-pick dry runs; every attempt was aborted and
the branch was never pushed.

## Baseline

| Item | Value |
|---|---|
| `origin/main` at start | `c52bb50` (#350) |
| Logo #3 on main | `41cef0c` — squash-merge of `brand-rollout-2` @ `4e6544c` (#346); preceded by #345 (`7fabac3`) |
| Main protection | required checks `backend`, `frontend`, `release gate (production schema parity)`; strict; enforce_admins |
| Remote branches scanned | 193 |

## Candidates

| Branch | Relation to main | Evidence | Status | Decision |
|---|---|---|---|---|
| `feat/brand-logo-individual-grid` (named in the task) | +36 / −19 vs main | The brand work it carried reached main through #345/#346 (squash). Unique remainder: `57fab75` (analytics mega-commit, 137 files), `7344d67`, `f66ccaf`/`a1dd76d`. Dry-run merge onto main conflicts. Open PR **#352** is `dirty` and its Workers Builds check fails. | VERIFIED (diverged, conflicting) | Not used as the working base. Not modified. #352 left untouched for its owner. |
| `brand-rollout-2` | Merged as #346 | Commits after the squash point that are not on main: `a660d03` (ConfitColors → `#111827`/coral), `e6c1753`, `dfca9f6`, `7459fdf`, `2797692` (conflicts on cherry-pick). | VERIFIED | Not merged. The intent of `a660d03` (official palette in `ConfitIcons`) was re-implemented on top of main using the official charcoal `#242526`, not `#111827`. |
| `feat/brand-csv-import-and-inventory` | Open PR **#351** | `backend` required check FAIL. | VERIFIED (blocked by CI) | Out of scope (feature work, not UI/UX). Untouched. |
| `review/all-features` | Draft PR **#353** | Docs only. | VERIFIED | No code to reconcile. |
| `part1-button-motion`, `fix/admin-audit-cleanup`, `010-clean` | Merged | `git cherry` shows no unmerged patches. | VERIFIED | Nothing to reconcile. |
| Other open PRs #343, #339, #336, #334 | — | Not in the branding / tokens / navigation / a11y surface touched here. | UNVERIFIED (not inspected in depth) | Untouched. |

## Decision

A new branch, **`feat/uiux-individual-grid-audit`**, was cut from `origin/main`
@ `c52bb50`, because:

1. Main already contains the Logo #3 rollout (#345/#346), so it is the most
   complete and the only conflict-free base.
2. `feat/brand-logo-individual-grid` conflicts with main and bundles an
   unrelated 137-file analytics commit; building on it would drag that into a
   UI/UX PR and inherit #352's failing state.
3. Updating #352 in place would have required a rebase/force-push of shared
   history, which the task forbids.

Complementary work was reconciled by re-implementing intent, not by
cherry-picking conflicting commits (see `brand-rollout-2` row).

## Limitations

- Workers Builds failures on #351/#352 are treated as environmental (they are not
  required checks on main); their root cause was not investigated.
- Open PRs #343/#339/#336/#334 were classified by title and changed-file list
  only.
