"""CONFIT virtual try-on benchmark harness.

Reproducible, offline-by-default evaluation of try-on candidates against the
acceptance rubric in docs/tryon/00-research-plan.md. This package is NOT on the
production request path; nothing here is imported by the API or the worker.

Honesty invariants (enforced in code):
- No candidate renders unless its adapter is explicitly enabled AND the required
  resource gate is opened (a real GPU, or a paid API key + an explicit opt-in).
- The default run is a dry run: it exercises the plumbing and produces NO try-on
  image (is_render=False). The scorer refuses to emit quality scores for any
  non-render, so a dry run or a gated adapter can never be mistaken for a result.
- Running real candidates needs resources behind approval gates (see the README).
"""
