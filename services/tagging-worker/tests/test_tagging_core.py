"""Feature 07 — product auto-tagging core tests.

Three layers, mirroring the other CONFIT workers' test discipline:

1. PURE LOGIC (no models): merge/corroboration, colour canonicalisation
   (incl. Arabic synonyms and the honest ``unmapped`` path), material
   normalisation, product-column mapping, refusal on nothing-to-tag,
   unresolved-axis reasons.
2. PIPELINE with INJECTED FAKES at the model boundary: deterministic fake
   CLIP (fixed logits per axis) and fake GLiNER (fixed entities) drive the
   REAL ProductTagger.tag() — pinning threshold gating, top-k, quality
   classification (full/image_only/text_only/none), provenance and the
   response contract.
3. REAL FashionCLIP on REAL production-catalogue photos (the same images
   the live test uses): the blazer/oxford/dress/trouser fixtures must be
   classified into the right platform category with honest confidence.

The real GLiNER model cannot load on the 2GB CI host (289M F32 ≈ 1.2GB) —
its behavioural validation runs against the DEPLOYED worker (live smoke,
EN + AR) which runs the identical pinned weights. That limitation is
recorded here on purpose: it is the honest boundary of this suite.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import List

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import tagging_core as core  # noqa: E402
from tagging_core import (  # noqa: E402
    AXIS_THRESHOLDS,
    COLOR_FAMILIES,
    GARMENT_LABELS,
    ProductTagger,
    TaggingRefused,
    _merge_tags,
    _product_suggestions,
    _norm,
    canonical_color,
    contains_arabic,
)

FIXTURES = HERE / "fixtures"


# ───────────────────────── 1. pure logic ─────────────────────────

class TestCanonicalColor:
    def test_english_synonyms_map_to_families(self):
        assert canonical_color("navy") == "Navy Blue"
        assert canonical_color("Dark Navy Blue") == "Navy Blue"
        assert canonical_color("burgundy") == "Burgundy"
        assert canonical_color("charcoal grey") == "Grey"

    def test_arabic_synonyms_map_to_families(self):
        assert canonical_color("كحلي") == "Navy Blue"
        assert canonical_color("أسود") == "Black"
        assert canonical_color("أخضر زمردي") == "Emerald Green"

    def test_longest_synonym_wins(self):
        # "navy blue" must beat the bare "blue" family
        assert canonical_color("navy blue") == "Navy Blue"

    def test_unmappable_color_is_none_not_a_guess(self):
        assert canonical_color("iridescent opal") is None
        assert canonical_color("") is None


class TestMaterialNormalisation:
    def test_common_aliases(self):
        from tagging_core import _normalise_material
        assert _normalise_material("Italian virgin wool") == "wool"
        assert _normalise_material("Genuine Leather") == "leather"
        assert _normalise_material("100% cotton poplin") == "cotton"
        assert _normalise_material("صوف إيطالي") == "wool"

    def test_unknown_passes_through_verbatim(self):
        from tagging_core import _normalise_material
        assert _normalise_material("seacell blend") == "seacell blend"


class TestMerge:
    def test_corroboration_keeps_higher_confidence_and_both_sources(self):
        image_tags = [{"axis": "color", "value": "navy", "confidence": 0.42, "source": "fashionclip"}]
        text_tags = [{"axis": "color", "value": "Navy", "confidence": 0.91, "source": "gliner"}]
        merged, unresolved = _merge_tags(image_tags, text_tags)
        assert len(merged) == 1
        assert merged[0]["confidence"] == 0.91
        assert set(merged[0]["corroborated_by"]) == {"fashionclip", "gliner"}

    def test_same_axis_different_values_both_kept(self):
        # image labels and text spans are different value spaces — both kept
        image_tags = [{"axis": "category", "value": "blazer", "confidence": 0.9, "source": "fashionclip"}]
        text_tags = [{"axis": "category", "value": "double-breasted blazer", "confidence": 0.8, "source": "gliner"}]
        merged, _ = _merge_tags(image_tags, text_tags)
        assert len(merged) == 2

    def test_unresolved_axes_report_honest_reasons(self):
        # only a colour tag exists -> the other axes must be explained
        tags = [{"axis": "color", "value": "navy", "confidence": 0.9, "source": "gliner"}]
        _, unresolved = _merge_tags([], tags)
        by_axis = {u["axis"]: u["reason"] for u in unresolved}
        # no image at all, and text was available but produced no
        # category/material entity — both halves of the story are told
        assert by_axis["category"] == "no_image+text_below_threshold"
        assert by_axis["material"] == "no_image+text_below_threshold"

    def test_no_inputs_at_all(self):
        _, unresolved = _merge_tags([], [])
        assert all(u["reason"] == "no_image+no_text" for u in unresolved)


class TestProductSuggestions:
    def test_text_color_wins_and_canonicalises(self):
        merged = [
            {"axis": "color", "value": "dark navy", "confidence": 0.7, "source": "gliner"},
            {"axis": "color", "value": "Navy Blue", "confidence": 0.5, "source": "fashionclip"},
        ]
        s = _product_suggestions(merged)
        assert s["color_family"] == "Navy Blue"
        assert "color_family_unmapped" not in s

    def test_text_color_wins_even_against_a_higer_confident_pixel_guess(self):
        # the documented merge policy: explicit marketing text outranks the
        # pixel guess regardless of confidence (they are not comparable
        # scales) — pinned by the 2026-10-03 live smoke, where FashionCLIP
        # "Blue" 0.94 wrongly beat GLiNER "dark navy" 0.92.
        merged = [
            {"axis": "color", "value": "Blue", "confidence": 0.94, "source": "fashionclip"},
            {"axis": "color", "value": "dark navy", "confidence": 0.92, "source": "gliner"},
        ]
        s = _product_suggestions(merged)
        assert s["color_family"] == "Navy Blue"

    def test_image_color_used_only_as_fallback(self):
        merged = [{"axis": "color", "value": "Metallic Gold", "confidence": 0.4, "source": "fashionclip"}]
        assert _product_suggestions(merged)["color_family"] == "Metallic Gold"

    def test_unmapped_text_color_is_reported_not_snapped(self):
        merged = [{"axis": "color", "value": "iridescent opal", "confidence": 0.8, "source": "gliner"}]
        s = _product_suggestions(merged)
        assert s["color_family"] == "iridescent opal"
        assert s["color_family_unmapped"] is True

    def test_text_material_beats_image_guess(self):
        merged = [
            {"axis": "material", "value": "virgin wool", "confidence": 0.6, "source": "gliner"},
            {"axis": "material", "value": "wool garment", "confidence": 0.9, "source": "fashionclip"},
        ]
        s = _product_suggestions(merged)
        assert s["material"] == "wool"

    def test_image_material_used_when_no_text(self):
        merged = [{"axis": "material", "value": "leather garment", "confidence": 0.8, "source": "fashionclip"}]
        assert _product_suggestions(merged)["material"] == "leather"

    def test_style_tags_from_pattern_and_category(self):
        merged = [
            {"axis": "pattern", "value": "checked plaid garment", "confidence": 0.6, "source": "fashionclip"},
            {"axis": "category", "value": "blazer", "confidence": 0.9, "source": "fashionclip"},
        ]
        s = _product_suggestions(merged)
        assert "plaid" in s["style_tags"] and "blazer" in s["style_tags"]

    def test_occasion_tags_from_both_sources(self):
        merged = [
            {"axis": "occasion", "value": "business office outfit", "confidence": 0.6, "source": "fashionclip"},
            {"axis": "occasion", "value": "evening dinner", "confidence": 0.7, "source": "gliner"},
        ]
        s = _product_suggestions(merged)
        assert "work" in s["occasion_tags"] and "evening dinner" in s["occasion_tags"]

    def test_platform_category_mapping(self):
        merged = [{"axis": "category", "value": "leather loafers", "confidence": 0.8, "source": "fashionclip"}]
        assert _product_suggestions(merged)["platform_category"] == "footwear"

    def test_absent_fields_mean_not_confident_not_default(self):
        # only a pattern tag -> no color/material/occasion keys AT ALL
        merged = [{"axis": "pattern", "value": "striped garment", "confidence": 0.9, "source": "fashionclip"}]
        s = _product_suggestions(merged)
        assert "color_family" not in s
        assert "material" not in s
        assert "occasion_tags" not in s


class TestRefusals:
    def test_nothing_to_tag_is_refused(self):
        tagger = ProductTagger(clip_model=object(), gliner_model=object())
        with pytest.raises(TaggingRefused) as ei:
            tagger.tag(image=None, title="", description="")
        assert ei.value.code == "NOTHING_TO_TAG"

    def test_text_only_is_accepted(self):
        tagger = _tagger_with_fakes(gliner_entities=[
            {"text": "navy", "label": "color", "score": 0.9},
        ])
        out = tagger.tag(image=None, title="Navy blazer")
        assert out["status"] == "completed"
        assert out["quality"] == "text_only"


# ───────────────────────── 2. pipeline with fakes ─────────────────────────

def _fake_clip(logits_by_axis):
    """Deterministic fake CLIP: returns the fixed softmax-ready logits for
    whichever axis prompt-count matches, so the REAL threshold gating and
    top-k logic in _classify_image runs unchanged."""

    class Out:
        def __init__(self, logits):
            import torch

            self.logits_per_image = torch.tensor([logits])

    class FakeClip:
        def __call__(self, **kwargs):
            import torch

            n = kwargs["input_ids"].shape[0] if "input_ids" in kwargs else 0
            # match axis by prompt count (each axis has a unique count)
            for count, logits in logits_by_axis.items():
                if count == n:
                    return Out(logits)
            return Out([1.0] * n)

    class FakeProc:
        def __call__(self, text, images, return_tensors="pt", padding=True):
            import torch

            return {"input_ids": torch.arange(len(text)).reshape(len(text), 1)}

    return FakeClip(), FakeProc()


def _fake_gliner(entities):
    class FakeGliner:
        def predict_entities(self, text, labels, threshold=0.5):
            return [e for e in entities if e["score"] >= threshold]

    return FakeGliner()


def _tagger_with_fakes(clip=None, proc=None, gliner_entities=None):
    return ProductTagger(
        clip_model=clip,
        image_processor=proc,
        gliner_model=_fake_gliner(gliner_entities or []),
    )


class TestPipelineWithFakes:
    def _full_fakes(self):
        # category axis: 39 prompts; blazer strongly wins
        clip, proc = _fake_clip({
            len(GARMENT_LABELS): [0.0] * len(GARMENT_LABELS),
        })
        # boost blazer
        logits = [0.0] * len(GARMENT_LABELS)
        logits[list(GARMENT_LABELS).index("blazer")] = 10.0
        clip, proc = _fake_clip({len(GARMENT_LABELS): logits})
        gliner = [
            {"text": "navy", "label": "color", "score": 0.93},
            {"text": "virgin wool", "label": "material", "score": 0.81},
            {"text": "Massimo Dutti", "label": "brand", "score": 0.72},
        ]
        tagger = ProductTagger(clip_model=clip, image_processor=proc, gliner_model=_fake_gliner(gliner))
        tagger._loaded = True
        return tagger

    def test_full_quality_with_provenance(self):
        tagger = self._full_fakes()
        img = (FIXTURES / "blazer_navy.jpg").read_bytes()
        out = tagger.tag(image=img, title="Massimo Dutti blazer", description="in navy virgin wool")
        assert out["quality"] == "full"
        assert out["status"] == "completed"
        sources = {t["source"] for t in out["tags"]}
        assert sources == {"fashionclip", "gliner"}
        # every tag carries its provenance
        for t in out["tags"]:
            assert {"axis", "value", "confidence", "source"} <= set(t)
        # text colour canonicalised into the suggestions
        assert out["product_suggestions"]["color_family"] == "Navy Blue"
        assert out["product_suggestions"]["material"] == "wool"
        assert out["product_suggestions"]["platform_category"] == "outerwear"
        # both models disclosed with licenses
        assert out["models"]["fashionclip"]["license"] == "mit"
        assert out["models"]["fashionclip"]["commercial"] is True
        assert out["models"]["gliner"]["license"] == "apache-2.0"
        assert out["models"]["gliner"]["used"] is True

    def test_threshold_gating_reports_unresolved_not_guesses(self):
        # uniform logits -> softmax uniform -> nothing clears threshold
        clip, proc = _fake_clip({len(GARMENT_LABELS): [0.0] * len(GARMENT_LABELS)})
        tagger = ProductTagger(clip_model=clip, image_processor=proc, gliner_model=_fake_gliner([]))
        tagger._loaded = True
        out = tagger.tag(image=(FIXTURES / "blazer_navy.jpg").read_bytes(), title="A thing")
        assert out["quality"] == "none"
        assert out["tag_count"] == 0
        unresolved_axes = {u["axis"] for u in out["axes_unresolved"]}
        assert {"category", "color", "material", "pattern", "occasion"} <= unresolved_axes
        assert out["product_suggestions"] == {}

    def test_image_only_quality(self):
        logits = [0.0] * len(GARMENT_LABELS)
        logits[list(GARMENT_LABELS).index("sneakers")] = 10.0
        clip, proc = _fake_clip({len(GARMENT_LABELS): logits})
        tagger = ProductTagger(clip_model=clip, image_processor=proc, gliner_model=_fake_gliner([]))
        tagger._loaded = True
        out = tagger.tag(image=(FIXTURES / "blazer_navy.jpg").read_bytes(), title="just a title")
        assert out["quality"] == "image_only"

    def test_gliner_entities_gated_by_score(self):
        gliner = [
            {"text": "navy", "label": "color", "score": 0.93},
            {"text": "ghost", "label": "brand", "score": 0.30},  # below gate
        ]
        tagger = ProductTagger(clip_model=None, image_processor=None, gliner_model=_fake_gliner(gliner))
        tagger._loaded = True
        out = tagger.tag(image=None, title="Navy thing by ghost")
        values = [t["value"] for t in out["tags"]]
        assert "navy" in values and "ghost" not in values

    def test_arabic_entities_carry_language(self):
        gliner = [{"text": "كحلي", "label": "color", "score": 0.9}]
        tagger = ProductTagger(clip_model=None, image_processor=None, gliner_model=_fake_gliner(gliner))
        tagger._loaded = True
        out = tagger.tag(image=None, title="بدلة كحلية")
        assert out["tags"][0]["language"] == "ar"
        assert out["text_language"] == "ar"
        assert out["product_suggestions"]["color_family"] == "Navy Blue"  # كحلي -> Navy


# ───────────────────────── 3. real FashionCLIP ─────────────────────────

class TestRealFashionClip:
    """Loads the real model once (module-scoped). GLiNER is NOT loaded here
    (2GB host limit) — its live validation is the deployed-worker smoke."""

    @pytest.fixture(scope="class")
    def real_tagger(self):
        tagger = ProductTagger()
        # load ONLY FashionCLIP (gliner would OOM on this host)
        import torch
        from transformers import CLIPModel, CLIPProcessor

        torch.set_num_threads(1)
        tagger._clip = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")
        tagger._clip_processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")
        tagger._clip.eval()
        tagger._gliner = None
        tagger._loaded = True
        return tagger

    @pytest.mark.parametrize("fixture,expected_labels", [
        ("blazer_navy.jpg", {"blazer", "suit jacket", "trench coat", "overcoat"}),
        ("leather_oxford_shoes.jpg", {"leather loafers", "boots", "sneakers", "dress shirt"}),
        ("silk_maxi_dress.jpg", {"maxi dress", "evening dress", "slip dress", "floral dress", "cocktail dress"}),
        ("wool_trousers.jpg", {"trousers", "tailored pants", "chinos", "jeans"}),
    ])
    def test_real_products_classify_into_right_category(self, real_tagger, fixture, expected_labels):
        out = real_tagger.tag(image=(FIXTURES / fixture).read_bytes())
        cat_tags = [t for t in out["tags"] if t["axis"] == "category"]
        assert cat_tags, f"no category tag cleared threshold for {fixture}"
        assert out["quality"] == "image_only"
        # the expected label family is represented in the confident top-3
        assert any(t["value"] in expected_labels for t in cat_tags), (
            f"{fixture}: got {[t['value'] for t in cat_tags]}, expected one of {expected_labels}"
        )
        # every confident tag respects its axis threshold
        for t in cat_tags:
            assert t["confidence"] >= AXIS_THRESHOLDS["category"]

    def test_response_contract_on_real_image(self, real_tagger):
        out = real_tagger.tag(image=(FIXTURES / "blazer_navy.jpg").read_bytes())
        for key in ("status", "quality", "tags", "tag_count", "axes_unresolved",
                    "product_suggestions", "models", "disclaimer", "timings"):
            assert key in out
        assert out["models"]["fashionclip"]["used"] is True
        assert out["models"]["gliner"]["used"] is False  # honest: not loaded here


# ───────────────────────── vocabulary sanity ─────────────────────────

class TestVocabularies:
    def test_every_garment_label_maps_to_a_real_platform_category(self):
        valid = {"outerwear", "tops", "bottoms", "dresses", "footwear", "accessories"}
        assert set(GARMENT_LABELS.values()) <= valid

    def test_every_pattern_and_occasion_label_has_a_tag(self):
        from tagging_core import PATTERN_STYLE_TAGS, OCCASION_TAGS, PATTERN_LABELS, OCCASION_LABELS
        assert set(PATTERN_STYLE_TAGS) == set(PATTERN_LABELS)
        assert set(OCCASION_TAGS) == set(OCCASION_LABELS)

    def test_thresholds_are_sane(self):
        for axis, thr in AXIS_THRESHOLDS.items():
            assert 0.05 <= thr <= 0.95, axis
