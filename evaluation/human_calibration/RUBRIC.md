# Sleeves + lower-garment application — rating rubric

Raters judge **the rendered output only** (with the input shown for
orientation). They do NOT see the gate verdict, the engine's own verify
flag, or any prior label.

## Item types

**Type S — sleeve integrity (57 items).** The catalog garment is declared
LONG-sleeve. Primary question:

> In the rendered image, do BOTH arms show the declared long sleeve
> reaching the wrist, with no visually missing/incomplete sleeve?

Primary judgment (one of):
- `FULL` — sleeves present on both arms, reach the wrist (cuff at the
  wrist may be slightly above it; a sliver of skin at the very wrist edge
  does not fail it).
- `PARTIAL` — a sleeve is visibly incomplete on at least one arm: ends
  short of the wrist, missing on one arm only, gap in the mid-forearm, or
  any other visually incomplete construction of a declared long sleeve.
- `ABSENT` — sleeves entirely missing (the person's own skin or original
  garment shows where the sleeve should be).
- `UNSURE` — cannot tell (state what is ambiguous).

Secondary fields (per item): confidence (1–5), one-line note (required if
not FULL).

**Type L — lower-garment application (7 items).** A bottom garment was
requested on top of the person's existing lower garment. Primary question:

> In the rendered image, was the requested bottom garment visibly
> replaced onto the person (or is the original bottom visibly unchanged)?

Primary judgment (one of):
- `APPLIED` — the requested bottom is clearly present and replaces the
  original (color/texture/shape matches the provided garment reference).
- `NOT_APPLIED` — the person is still wearing the original bottom; no
  visible change to the lower garment.
- `PARTIAL_APPLIED` — lower garment changed in places but not fully
  replaced (state where).
- `UNSURE` — cannot tell (low contrast is expected in some items; state
  that).

Secondary: confidence (1–5), note.

## Rules

1. Judge the RENDER, not the garment reference alone. The reference is
   provided so "requested garment" is identifiable.
2. Low contrast is a real condition, not an error: if the render and the
   original bottom are nearly identical and you cannot detect a change,
   the honest answer is `UNSURE` with the note "cannot distinguish" —
   do NOT guess.
3. Do not use any AI tool to inspect the images.
4. Items are presented in the randomized order in the manifest
   (`display_order`); do not skip ahead.
5. If an image fails to load, mark `ITEM_ERROR` and continue.
6. One session per rater is not required — but each item must be judged by
   each rater exactly once, unaided.

## What raters are explicitly NOT judging

- Overall photo quality, pose, or aesthetics (out of scope).
- Face/identity match (separate, license-gated track).
- Whether the engine "should" have applied the garment (product semantics
  — the rubric asks what IS visibly the case, only).
