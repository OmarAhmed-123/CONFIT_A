"""Who a garment is for, and whether it may appear in a requested outfit.

THE DEFECT THIS EXISTS FOR
--------------------------
Measured on production, 2026-09-30:

    "mens casual weekend look, shirt and trousers"
    -> outfit #101 containing "Strappy Metallic Leather Heeled Sandals"

A men's request returned women's heeled sandals. Not a ranking weakness —
`products` had **no gender column at all**. The only "gender" in the
codebase was `gender_mode`, a try-on RENDER parameter describing the photo,
never an attribute of the garment. The styling engine was structurally
unable to honour the request, so it ignored it.

DESIGN
------
Three values only: `mens`, `womens`, `unisex`. Finer taxonomies (boys,
maternity, petite) imply a precision this catalogue does not carry and
would mostly resolve to `unisex` anyway.

`unisex` is the DEFAULT and is deliberately permissive: a poplin shirt or
tapered trousers genuinely suit anyone, and excluding them from a men's
outfit would leave the composer unable to build one. The filter therefore
removes only garments belonging to the OTHER specific gender.

Inference is keyword-based and deterministic, not a model. The signal here
is the garment noun itself ("tuxedo", "necktie", "clutch"), which is exactly
what keywords capture well — a model would add latency and non-determinism
for a decision that is already unambiguous. Where the noun is genuinely
neutral, `unisex` is the honest answer rather than a guess.
"""
from __future__ import annotations

import re
from typing import Optional

MENS = "mens"
WOMENS = "womens"
UNISEX = "unisex"

VALID_GENDERS = (MENS, WOMENS, UNISEX)

#: Garment nouns that carry gender in ordinary retail usage. Longest and
#: most specific first — "dinner jacket" must not be read as "jacket".
_MENS_TERMS = (
    "tuxedo", "dinner jacket", "necktie", "neck tie", "bow tie", "cravat",
    "oxford shoe", "derby shoe", "brogue", "loafer", "chinos",
    "polo shirt", "waistcoat", "suit trouser", "pocket square", "cufflink",
    "menswear", " mens ", " men ",
)
_WOMENS_TERMS = (
    "dress", "gown", "skirt", "blouse", "clutch", "heeled", "heels",
    "stiletto", "pump", "sandal", "handbag", "tote bag", "camisole",
    "jumpsuit", "bodysuit", "maxi", "midi", "kaftan", "abaya",
    "womenswear", " womens ", " ladies ", " female ",
)

#: What the SHOPPER asked for. Arabic included because the storefront is
#: Arabic-first: `_OCCASION_KEYWORDS` being English-only is the same bug
#: class that made Arabic queries return nothing at all.
_QUERY_MENS = (
    "mens", "men's", "for men", "menswear", "male", "guy", "gentleman",
    "رجالي", "رجالى", "للرجال", "راجل", "رجل",
)
_QUERY_WOMENS = (
    "womens", "women's", "for women", "womenswear", "ladies", "female",
    "حريمي", "حريمى", "للستات", "نسائي", "نسائى", "ست",
)

_WORD = re.compile(r"[^\w\u0600-\u06FF]+")
#: Apostrophes are DELETED, not turned into spaces. Splitting on them made
#: "men's" become "men s", which matched neither "mens" nor "men's" and let
#: the most common English phrasing fall through to no-gender.
_APOSTROPHE = re.compile(r"[\u2019\u02BC']")


def _normalise(text: Optional[str]) -> str:
    cleaned = _APOSTROPHE.sub("", (text or "").lower())
    return f" {_WORD.sub(' ', cleaned).strip()} "


def infer_gender(title: Optional[str], category_slug: Optional[str] = None) -> str:
    """Classify a garment from its own name.

    Checked women's-first for the nouns that are unambiguous, then men's.
    A tie between signals resolves to `unisex`: claiming a gender we cannot
    read is what produced the heeled-sandals bug in reverse.
    """
    haystack = _normalise(title) + _normalise(category_slug)

    # Garment nouns DO match as substrings on purpose: "heeled" must fire
    # inside "Heeled Sandals", and "dress" inside "Maxi Dress with Drape".
    # The query side cannot do this — see `_contains_phrase`.
    mens_hit = any(t in haystack for t in _MENS_TERMS)
    womens_hit = any(t in haystack for t in _WOMENS_TERMS)

    if mens_hit and not womens_hit:
        return MENS
    if womens_hit and not mens_hit:
        return WOMENS
    # Both or neither: the name does not tell us, so say so.
    return UNISEX


def _contains_phrase(haystack: str, phrase: str) -> bool:
    """Whole-token match, never a substring.

    Substring matching classified "womens evening dress" as MENSWEAR,
    because "womens" literally contains "mens". Every token here is
    surrounded by spaces by `_normalise`, so bounding the phrase the same
    way makes the comparison exact.
    """
    return f" {phrase.strip()} " in haystack


def gender_from_query(text: Optional[str]) -> Optional[str]:
    """What the shopper asked for, or None when they did not say.

    None is meaningful: an unqualified request must not be silently
    narrowed to one gender, which would hide half the catalogue.
    """
    haystack = _normalise(text)
    mens = any(_contains_phrase(haystack, t) for t in _QUERY_MENS)
    womens = any(_contains_phrase(haystack, t) for t in _QUERY_WOMENS)
    if mens and not womens:
        return MENS
    if womens and not mens:
        return WOMENS
    return None


def is_compatible(product_gender: Optional[str], requested: Optional[str]) -> bool:
    """May this garment appear in an outfit for `requested`?

    Permissive by design:
      - no request      -> everything is eligible
      - unisex garment  -> always eligible
      - otherwise       -> only an exact match

    Excluding unisex items from a gendered request would leave the composer
    with too few slots to build a complete outfit, which is a worse failure
    than showing a neutral shirt.
    """
    if not requested:
        return True
    gender = (product_gender or UNISEX).strip().lower()
    if gender not in VALID_GENDERS:
        # An unrecognised stored value is treated as unisex rather than
        # dropped: a bad backfill must not empty the catalogue.
        return True
    return gender in (UNISEX, requested)
