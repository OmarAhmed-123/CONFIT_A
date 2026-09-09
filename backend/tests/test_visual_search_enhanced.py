"""
Tests for Deterministic Visual Search Enhancement

Tests cover:
A. Synonym normalization
B. Category hierarchy matching
C. Color similarity (LAB color space)
D. Style/tag weighting
E. Enhanced scoring
"""

import pytest
from backend.app.services.visual_search_enhanced import (
    normalize_synonym,
    expand_synonyms,
    get_category_match_level,
    get_color_similarity,
    get_style_similarity,
    calculate_enhanced_score,
    rgb_to_lab,
    lab_distance,
)


# =============================================================================
# A. SYNONYM NORMALIZATION TESTS
# =============================================================================

class TestSynonymNormalization:
    """Test synonym normalization functions."""
    
    def test_exact_match(self):
        """Exact term should return itself."""
        assert normalize_synonym("t-shirt") == "t-shirt"
        assert normalize_synonym("pants") == "pants"
    
    def test_synonym_mapping(self):
        """Synonyms should map to canonical forms."""
        assert normalize_synonym("tee") == "t-shirt"
        assert normalize_synonym("trousers") == "pants"
        assert normalize_synonym("trainers") == "sneakers"
        assert normalize_synonym("frock") == "dress"
    
    def test_case_insensitive(self):
        """Synonym mapping should be case-insensitive."""
        assert normalize_synonym("Tee") == "t-shirt"
        assert normalize_synonym("TROUSERS") == "pants"
    
    def test_empty_input(self):
        """Empty input should return empty."""
        assert normalize_synonym("") == ""
        assert normalize_synonym(None) is None
    
    def test_unknown_term(self):
        """Unknown terms should return themselves."""
        assert normalize_synonym("widget") == "widget"
    
    def test_expand_synonyms(self):
        """expand_synonyms should return all synonymous terms."""
        synonyms = expand_synonyms("tee")
        assert "t-shirt" in synonyms
        assert "tee" in synonyms
        assert "tshirt" in synonyms
    
    def test_expand_synonyms_canonical(self):
        """Canonical form should expand to include all synonyms."""
        synonyms = expand_synonyms("t-shirt")
        assert "tee" in synonyms
        assert "t-shirt" in synonyms


# =============================================================================
# B. CATEGORY HIERARCHY TESTS
# =============================================================================

class TestCategoryHierarchy:
    """Test category hierarchy matching."""
    
    def test_exact_match(self):
        """Exact category match should return 1.0."""
        score, match_type = get_category_match_level("tops", "tops")
        assert score == 1.0
        assert match_type == "exact"
    
    def test_child_match(self):
        """Child category should return 0.7."""
        score, match_type = get_category_match_level("tops", "shirt")
        assert score == 0.7
        assert match_type == "child"
    
    def test_parent_match(self):
        """Parent category should return 0.7."""
        score, match_type = get_category_match_level("shirt", "tops")
        assert score == 0.7
        assert match_type == "parent"
    
    def test_related_match(self):
        """Related category should return 0.15."""
        score, match_type = get_category_match_level("tops", "outerwear")
        assert score == 0.15
        assert match_type == "related"
    
    def test_no_match(self):
        """Unrelated categories should return 0.0."""
        score, match_type = get_category_match_level("tops", "footwear")
        assert score == 0.0
        assert match_type == "none"
    
    def test_empty_input(self):
        """Empty input should return 0.0."""
        score, match_type = get_category_match_level("", "tops")
        assert score == 0.0
        assert match_type == "none"
    
    def test_case_insensitive(self):
        """Category matching should be case-insensitive."""
        score, match_type = get_category_match_level("Tops", "tops")
        assert score == 1.0
        assert match_type == "exact"


# =============================================================================
# C. COLOR SIMILARITY TESTS
# =============================================================================

class TestColorSimilarity:
    """Test color similarity functions."""
    
    def test_exact_match(self):
        """Exact color match should return 1.0."""
        assert get_color_similarity("navy", "navy") == 1.0
    
    def test_color_family_match(self):
        """Colors in same family should return 0.9."""
        assert get_color_similarity("navy", "dark blue") == 0.9
    
    def test_similar_colors(self):
        """Similar colors should have high similarity."""
        sim = get_color_similarity("navy", "blue")
        assert sim > 0.5
    
    def test_different_colors(self):
        """Different colors should have lower similarity than same color."""
        sim_diff = get_color_similarity("black", "white")
        sim_same = get_color_similarity("black", "black")
        assert sim_diff < sim_same  # Different colors should be less similar than same color
        assert sim_diff > 0.0  # But still have some similarity (they're both neutral)
    
    def test_empty_input(self):
        """Empty input should return 0.0."""
        assert get_color_similarity("", "navy") == 0.0
        assert get_color_similarity("navy", "") == 0.0
    
    def test_case_insensitive(self):
        """Color matching should be case-insensitive."""
        assert get_color_similarity("Navy", "navy") == 1.0
    
    def test_rgb_to_lab(self):
        """RGB to LAB conversion should work."""
        lab = rgb_to_lab((0, 0, 128))  # navy
        assert lab[0] > 0  # L should be positive
        assert isinstance(lab[0], float)
    
    def test_lab_distance(self):
        """LAB distance should be calculated correctly."""
        lab1 = rgb_to_lab((0, 0, 0))  # black
        lab2 = rgb_to_lab((255, 255, 255))  # white
        distance = lab_distance(lab1, lab2)
        assert distance > 0


# =============================================================================
# D. STYLE SIMILARITY TESTS
# =============================================================================

class TestStyleSimilarity:
    """Test style similarity functions."""
    
    def test_exact_match(self):
        """Exact style match should return 1.0."""
        assert get_style_similarity("casual", "casual") == 1.0
    
    def test_related_styles(self):
        """Related styles should return 0.7."""
        assert get_style_similarity("casual", "everyday") == 0.7
    
    def test_opposite_styles(self):
        """Opposite styles should return 0.0."""
        assert get_style_similarity("casual", "formal") == 0.0
    
    def test_different_styles(self):
        """Different styles should return 0.1."""
        sim = get_style_similarity("casual", "bohemian")
        assert sim == 0.1
    
    def test_empty_input(self):
        """Empty input should return 0.0."""
        assert get_style_similarity("", "casual") == 0.0
    
    def test_case_insensitive(self):
        """Style matching should be case-insensitive."""
        assert get_style_similarity("Casual", "casual") == 1.0


# =============================================================================
# E. ENHANCED SCORING TESTS
# =============================================================================

class TestEnhancedScoring:
    """Test enhanced scoring function."""
    
    def test_exact_match_high_score(self):
        """Exact category, color, style match should give high score."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="navy",
            product_style_tags="smart casual, tailored",
            product_title="Navy Blazer",
            analysis_available=True,
        )
        assert score >= 65  # With adjusted weights, exact match gives reasonable score
        assert breakdown["category"] > 0
        assert breakdown["color"] > 0
        assert breakdown["style"] > 0
    
    def test_no_match_base_score(self):
        """No category match should give low score."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="footwear",
            product_color="black",
            product_style_tags="streetwear",
            product_title="Sneakers",
            analysis_available=True,
        )
        # Low base (20) + some color/style similarity
        assert score >= 20.0  # At least base score
        assert score < 60.0  # But not high since no category match
        assert breakdown["category"] == 0.0  # No category match
    
    def test_category_hierarchy_bonus(self):
        """Child category should get bonus."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="shirt",  # child of tops
            product_color="navy",
            product_style_tags="smart casual",
            product_title="Dress Shirt",
            analysis_available=True,
        )
        assert score > 70  # Should have category bonus
    
    def test_synonym_normalization(self):
        """Synonyms should be normalized."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="t-shirt",  # normalized from "tee"
            product_color="navy",
            product_style_tags="casual",
            product_title="T-Shirt",
            analysis_available=True,
        )
        assert score > 50  # Should match via synonym with adjusted weights
    
    def test_color_similarity_bonus(self):
        """Similar colors should get bonus."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="dark blue",  # similar to navy
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="navy",
            product_style_tags="smart casual",
            product_title="Blazer",
            analysis_available=True,
        )
        assert score > 70  # Should have color similarity bonus
    
    def test_analysis_unavailable(self):
        """When analysis unavailable, should return base score."""
        score, breakdown = calculate_enhanced_score(
            detected_category=None,
            detected_color=None,
            detected_style=None,
            detected_pattern=None,
            product_category="tops",
            product_color="navy",
            product_style_tags="smart casual",
            product_title="Blazer",
            analysis_available=False,
        )
        assert score == 20.0  # Adjusted base score
        assert breakdown["category"] == 0.0
        assert breakdown["color"] == 0.0
        assert breakdown["style"] == 0.0
    
    def test_max_score_cap(self):
        """Score should not exceed maximum."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="navy",
            product_style_tags="smart casual, tailored, elegant",
            product_title="Perfect Navy Blazer",
            analysis_available=True,
        )
        assert score <= 98.0
    
    def test_deterministic_tie_breaking(self):
        """Same score should be broken by category and color scores."""
        # Two products with same base score but different breakdowns
        score1, breakdown1 = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="navy",
            product_style_tags="casual",
            product_title="Product A",
            analysis_available=True,
        )
        
        score2, breakdown2 = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Smart Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="navy",
            product_style_tags="casual",
            product_title="Product B",
            analysis_available=True,
        )
        
        # Same inputs should give same score (deterministic)
        assert score1 == score2
        assert breakdown1 == breakdown2


# =============================================================================
# F. REGRESSION TESTS
# =============================================================================

class TestRegression:
    """Regression tests for edge cases."""
    
    def test_empty_vision_output(self):
        """Empty vision output should not crash."""
        score, breakdown = calculate_enhanced_score(
            detected_category=None,
            detected_color=None,
            detected_style=None,
            detected_pattern=None,
            product_category="tops",
            product_color="navy",
            product_style_tags="smart casual",
            product_title="Blazer",
            analysis_available=False,
        )
        assert score == 20.0  # Adjusted base score
    
    def test_unknown_category(self):
        """Unknown category should not match."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Swimwear",  # unknown
            detected_color="blue",
            detected_style="Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="blue",
            product_style_tags="casual",
            product_title="Shirt",
            analysis_available=True,
        )
        assert breakdown["category"] == 0.0
    
    def test_unknown_color(self):
        """Unknown color should use LAB distance."""
        score, breakdown = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="teal",  # unknown in map
            detected_style="Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="blue",
            product_style_tags="casual",
            product_title="Shirt",
            analysis_available=True,
        )
        # Should still get some color score via LAB distance
        assert score >= 50.0
    
    def test_empty_catalog(self):
        """Empty catalog should return empty results."""
        # This is handled by the service layer, not the scoring function
        pass
    
    def test_duplicate_products(self):
        """Duplicate products should get same score."""
        score1, _ = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="navy",
            product_style_tags="casual",
            product_title="Product A",
            analysis_available=True,
        )
        score2, _ = calculate_enhanced_score(
            detected_category="Tops",
            detected_color="navy",
            detected_style="Casual",
            detected_pattern="Solid",
            product_category="tops",
            product_color="navy",
            product_style_tags="casual",
            product_title="Product A",  # same product
            analysis_available=True,
        )
        assert score1 == score2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
