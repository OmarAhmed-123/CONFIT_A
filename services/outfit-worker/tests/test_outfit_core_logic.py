"""Feature 06 — outfit worker core tests: PURE LOGIC layer (no torch).

The real OutfitTransformer checkpoints (769MB each) cannot load on the 2GB
CI host — same honest boundary as the tagging worker's GLiNER. What CAN and
MUST be pinned locally, without any model:

1. slot → Polyvore category mapping (the model's training vocabulary),
   including the honest `unknown` pass-through for unmapped slots;
2. type-aware structural analysis: duplicate exclusive slots, coverage with
   the full-body alternative, warnings;
3. the TATTOO-style axis math: identical profiles → 1.0, orthogonal → ~0,
   single item → None (undefined, never faked), zero vector → None;
4. refusal validation: <2 items for compatibility, empty candidates for
   FITB, hard ceilings;
5. response-block rendering: 0-100 ints, null axes, method labeling.

The REAL model's behaviour (does a coherent outfit actually outscore a
clashing one? does FITB rank the right completion first?) is validated
against the DEPLOYED worker by test_deployed_type_aware_eval.py — the
type-aware evaluation discipline of TATTOO (arXiv:2509.23242).
"""
from __future__ import annotations

import sys

import pytest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import outfit_core as oc  # noqa: E402


# ── slot → polyvore mapping ───────────────────────────────────────────


class TestSlotMapping:
    def test_core_slots_map_to_polyvore(self):
        assert oc.slot_to_polyvore("upper_inner") == "tops"
        assert oc.slot_to_polyvore("upper_outer") == "outerwear"
        assert oc.slot_to_polyvore("lower") == "bottoms"
        assert oc.slot_to_polyvore("footwear") == "shoes"
        assert oc.slot_to_polyvore("full_body") == "all-body"

    def test_accessory_family_collapses_to_accessories(self):
        for slot in ("accessory", "accessory_waist", "accessory_neck",
                     "accessory_hand", "accessory_head", "accessory_light"):
            assert oc.slot_to_polyvore(slot) == "accessories"

    def test_polyvore_names_pass_through(self):
        for name in ("tops", "bottoms", "shoes", "outerwear", "all-body",
                     "accessories", "bags"):
            assert oc.slot_to_polyvore(name) == name

    def test_unknown_slot_is_honest_not_guessed(self):
        assert oc.slot_to_polyvore("hats") == "unknown"
        assert oc.slot_to_polyvore("") == "unknown"
        assert oc.slot_to_polyvore(None) == "unknown"
        assert oc.slot_to_polyvore("  Upper_Inner ") == "tops"  # case/space

    def test_normalize_slot_lowercases_and_trims(self):
        assert oc.normalize_slot("  FootWear ") == "footwear"
        assert oc.normalize_slot(None) == ""


# ── type-aware structural analysis ────────────────────────────────────


class TestAnalyzeTypes:
    def test_clean_three_piece_outfit(self):
        result = oc.analyze_types(["upper_inner", "lower", "footwear"])
        assert result["duplicate_slots"] == []
        assert result["coverage"]["has_upper"] is True
        assert result["coverage"]["has_lower_or_full_body"] is True
        assert result["coverage"]["has_footwear"] is True
        assert result["coverage"]["missing_essentials"] == []
        assert result["warnings"] == []
        assert result["polyvore_categories"] == ["tops", "bottoms", "shoes"]

    def test_duplicate_exclusive_slot_flagged(self):
        result = oc.analyze_types(["upper_inner", "upper_inner", "lower"])
        assert result["duplicate_slots"] == ["upper_inner"]
        assert any("upper_inner" in w for w in result["warnings"])

    def test_accessories_are_not_exclusive(self):
        result = oc.analyze_types(
            ["upper_inner", "lower", "accessory_neck", "accessory_hand"])
        assert result["duplicate_slots"] == []
        assert result["warnings"] == []

    def test_full_body_replaces_top_and_bottom(self):
        result = oc.analyze_types(["full_body", "footwear"])
        assert result["coverage"]["missing_essentials"] == []
        assert result["polyvore_categories"] == ["all-body", "shoes"]

    def test_full_body_without_shoes(self):
        result = oc.analyze_types(["full_body"])
        assert result["coverage"]["missing_essentials"] == ["footwear"]

    def test_incomplete_outfit_reports_missing_essentials(self):
        result = oc.analyze_types(["upper_inner"])
        assert set(result["coverage"]["missing_essentials"]) == {"lower", "footwear"}

    def test_full_body_plus_top_and_bottom_warns(self):
        result = oc.analyze_types(["full_body", "upper_inner", "lower"])
        assert any("full-body garment" in w for w in result["warnings"])

    def test_no_slots_at_all_is_reported(self):
        result = oc.analyze_types(["", None, ""])
        assert result["slots"] == ["", "", ""]
        assert any("could not run" in w for w in result["warnings"])


# ── TATTOO-style axis math ────────────────────────────────────────────


class TestAxisMath:
    def test_identical_profiles_score_one(self):
        p = [0.25, 0.75, 0.0]
        assert oc.axis_profiles_to_coherence([p, p, p]) == pytest.approx(1.0)

    def test_two_identical_items(self):
        p = [1.0, 0.0]
        assert oc.axis_profiles_to_coherence([p, p]) == pytest.approx(1.0)

    def test_orthogonal_profiles_score_zero(self):
        # disjoint supports → cosine 0
        assert oc.axis_profiles_to_coherence([[1, 0], [0, 1]]) == 0.0

    def test_single_item_is_none_not_faked(self):
        assert oc.axis_profiles_to_coherence([[0.5, 0.5]]) is None

    def test_empty_is_none(self):
        assert oc.axis_profiles_to_coherence([]) is None

    def test_zero_vector_is_none(self):
        assert oc.axis_profiles_to_coherence([[0, 0], [1, 0]]) is None

    def test_clamped_into_unit_range(self):
        # adversarial: negative 'probabilities' cannot push outside [0,1]
        val = oc.axis_profiles_to_coherence([[-1, 0], [1, 0]])
        assert 0.0 <= val <= 1.0

    def test_partial_agreement_is_between_zero_and_one(self):
        a = [0.9, 0.1]
        b = [0.1, 0.9]
        val = oc.axis_profiles_to_coherence([a, b])
        assert 0.0 < val < 1.0

    def test_all_axes_have_anchors(self):
        expected = {"color", "style", "season", "occasion", "material", "balance"}
        assert set(oc.AXIS_ANCHORS) == expected
        for axis, anchors in oc.AXIS_ANCHORS.items():
            assert 4 <= len(anchors) <= 12, axis
            assert len(set(anchors)) == len(anchors), axis

    def test_summarize_axes_renders_ints_and_nulls(self):
        block = oc.summarize_axes({
            "color": 0.876, "style": None, "season": 0.0,
        })
        assert block["axes"]["color"] == 88
        assert block["axes"]["style"] is None
        assert block["axes"]["season"] == 0
        assert block["overall"] == 44  # mean(88, 0)
        assert block["method"] == "clip_text_anchor_projection"
        assert "TATTOO" in block["inspired_by"]
        assert "NOT the paper's MLLM pipeline" in block["inspired_by"]
        assert block["disclaimer"]

    def test_summarize_axes_all_null(self):
        block = oc.summarize_axes({"color": None, "style": None})
        assert block["overall"] is None


# ── refusals ──────────────────────────────────────────────────────────


class TestRefusals:
    def test_compat_needs_two_items(self):
        try:
            oc._validate_item_counts(1, None, mode="compatibility")
            raised = None
        except oc.OutfitEngineRefused as exc:
            raised = exc
        assert raised is not None and raised.code == "INVALID_OUTFIT"

    def test_compat_ceiling(self):
        try:
            oc._validate_item_counts(17, None, mode="compatibility")
            raised = None
        except oc.OutfitEngineRefused as exc:
            raised = exc
        assert raised is not None and raised.code == "TOO_MANY_ITEMS"

    def test_compat_valid_range_passes(self):
        oc._validate_item_counts(2, None, mode="compatibility")
        oc._validate_item_counts(16, None, mode="compatibility")

    def test_fitb_accepts_single_item_outfit(self):
        oc._validate_item_counts(1, 3, mode="fitb")

    def test_fitb_needs_candidates(self):
        try:
            oc._validate_item_counts(2, 0, mode="fitb")
            raised = None
        except oc.OutfitEngineRefused as exc:
            raised = exc
        assert raised is not None and raised.code == "NO_CANDIDATES"

    def test_fitb_candidate_ceiling(self):
        try:
            oc._validate_item_counts(2, 65, mode="fitb")
            raised = None
        except oc.OutfitEngineRefused as exc:
            raised = exc
        assert raised is not None and raised.code == "TOO_MANY_CANDIDATES"


# ── engine shape (torch-free surface only) ────────────────────────────


class TestEngineSurface:
    def test_engine_construction_is_torch_free(self):
        engine = oc.OutfitEngine(device="cpu")
        assert engine.compat_loaded is False
        assert engine.complementary_loaded is False
        assert engine.compat_model is None
        assert engine.complementary_model is None

    def test_missing_checkpoint_refuses_honestly(self, tmp_path, monkeypatch):
        # Point the weights dir at an empty dir: load must REFUSE with
        # CHECKPOINT_MISSING, not fall back to any invented behaviour.
        monkeypatch.setenv("OUTFIT_WEIGHTS_DIR", str(tmp_path))
        import importlib
        importlib.reload(oc)
        engine = oc.OutfitEngine(device="cpu")
        try:
            engine.load_compat()
            raised = None
        except oc.OutfitEngineRefused as exc:
            raised = exc
        assert raised is not None and raised.code == "CHECKPOINT_MISSING"
        importlib.reload(oc)  # restore default paths for other tests

    def test_disclosure_names_models_and_licenses(self):
        assert oc._MODELS_DISCLOSURE["outfit_transformer"]["license"] == "mit"
        assert oc._MODELS_DISCLOSURE["outfit_transformer"]["commercial"] is True
        assert oc._MODELS_DISCLOSURE["fashionclip"]["license"] == "mit"
        assert "eef4be5" in oc._MODELS_DISCLOSURE["outfit_transformer"]["implementation"]
        assert "Polyvore" in oc._TRAINING_NOTE
