"""Baseline job matrix generator (Phase 0.5, §24-26).

Paired evaluation: same person + garment + preprocessing + resolution across
arms. Arms:
  SINGLE — FASHN single-garment baseline (production-identical behavior).
  N2_TB  — chained top+bottom (client-side chain: layer-1 output is layer-2
           person input). This is the N=2 production-candidate regime.
  N2_IO  — chained inner+outer.
  N2_WC  — N=2 chain worst-case (bulky over slim).
  N3     — chained 3 layers (EVAL REGIME ONLY, never a production claim).
  N3_WC  — N=3 chain worst-case (long over short, coat over jacket).

Chaining is CLIENT-SIDE (same pattern the CONFIT backend already uses for
sequential layering); ZERO production code change.
"""
from __future__ import annotations

import json
from pathlib import Path

EVAL_ROOT = Path(__file__).resolve().parent.parent


def _p(i: int) -> str:
    return f"p{int(i):03d}"


def build_matrix() -> list[dict]:
    outfits = []
    # ---- SINGLE (24): each garment once, person rotated over p001..p010
    garments = [f"g{i:03d}" for i in range(1, 25)]
    slots = {"g001": "upper_inner", "g002": "upper_inner", "g003": "upper_inner",
             "g004": "upper_inner", "g005": "upper_inner", "g006": "upper_inner",
             "g007": "upper_inner", "g008": "upper_inner", "g009": "upper_inner",
             "g010": "upper_inner", "g011": "upper_inner", "g012": "upper_inner",
             "g013": "upper_inner", "g014": "upper_outer", "g015": "upper_outer",
             "g016": "upper_outer", "g017": "upper_outer", "g018": "upper_inner",
             "g019": "upper_inner", "g020": "lower", "g021": "lower",
             "g022": "lower", "g023": "lower", "g024": "dress"}
    for i, g in enumerate(garments):
        outfits.append({
            "outfit_id": f"S_{g}", "arm": "SINGLE", "person_id": _p(1 + i % 10),
            "layers": [{"garment_id": g, "slot": slots[g], "order": 1}],
        })
    # ---- N2 top+bottom (7 jobs)
    tb = [
        ("g001", "g020", "p001"), ("g001", "g020", "p009"),
        ("g005", "g021", "p002"), ("g005", "g021", "p010"),
        ("g013", "g023", "p003"),  # light-on-light
        ("g012", "g022", "p004"),  # dark-on-dark
        ("g003", "g020", "p005"),  # similar-color pair
    ]
    for i, (t, b, person) in enumerate(tb):
        outfits.append({
            "outfit_id": f"TB_{i:02d}_{t}_{b}", "arm": "N2_TB", "person_id": person,
            "layers": [
                {"garment_id": t, "slot": "upper_inner", "order": 1},
                {"garment_id": b, "slot": "lower", "order": 2},
            ],
            "pairing": "top+bottom",
        })
    # ---- N2 inner+outer (3 jobs)
    io = [
        ("g010", "g017", "p001"),  # long inner + outer
        ("g010", "g017", "p009"),
        ("g011", "g015", "p010"),  # shirt + short jacket
    ]
    for i, (inn, out, person) in enumerate(io):
        outfits.append({
            "outfit_id": f"IO_{i:02d}_{inn}_{out}", "arm": "N2_IO", "person_id": person,
            "layers": [
                {"garment_id": inn, "slot": "upper_inner", "order": 1},
                {"garment_id": out, "slot": "upper_outer", "order": 2},
            ],
            "pairing": "inner+outer",
        })
    # ---- N2 worst-case bulky over slim (2 jobs)
    outfits.append({
        "outfit_id": "WC_BULKY_g018_g019", "arm": "N2_WC", "person_id": "p006",
        "layers": [
            {"garment_id": "g018", "slot": "upper_inner", "order": 1},
            {"garment_id": "g019", "slot": "upper_inner", "order": 2},
        ],
        "pairing": "bulky_over_slim_stress",
    })
    outfits.append({
        "outfit_id": "WC_DARK_g002_g016", "arm": "N2_WC", "person_id": "p007",
        "layers": [
            {"garment_id": "g002", "slot": "upper_inner", "order": 1},
            {"garment_id": "g016", "slot": "upper_outer", "order": 2},
        ],
        "pairing": "dark_on_dark_inner_outer",
    })
    # ---- N3 chains (EVAL ONLY)
    outfits.append({
        "outfit_id": "N3_A_g010_g017_g021", "arm": "N3", "person_id": "p002",
        "layers": [
            {"garment_id": "g010", "slot": "upper_inner", "order": 1},
            {"garment_id": "g017", "slot": "upper_outer", "order": 2},
            {"garment_id": "g021", "slot": "lower", "order": 3},
        ],
        "pairing": "long_inner_then_outer_then_bottom",
    })
    outfits.append({
        "outfit_id": "N3_WC_LONGSHORT_g016_g015_g020", "arm": "N3_WC", "person_id": "p003",
        "layers": [
            {"garment_id": "g016", "slot": "upper_outer", "order": 1},
            {"garment_id": "g015", "slot": "upper_outer", "order": 2},
            {"garment_id": "g020", "slot": "lower", "order": 3},
        ],
        "pairing": "long_over_short_chain_stress",
    })
    return outfits


def main():
    outfits = build_matrix()
    n_inferences = sum(len(o["layers"]) for o in outfits)
    out = EVAL_ROOT / "fixtures" / "outfits.json"
    out.write_text(json.dumps({"outfits": outfits, "n_outfits": len(outfits),
                               "n_inferences": n_inferences}, indent=2))
    print(f"WROTE {len(outfits)} outfits / {n_inferences} inferences -> {out}")


if __name__ == "__main__":
    main()
