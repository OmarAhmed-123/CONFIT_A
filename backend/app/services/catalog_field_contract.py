"""One authoritative field contract for every catalogue write path.

The importer has four entry points — CSV preview, JSON import, the background
worker that replays a queued job, and the brand API that reads the result — and
before this module each of them carried its own idea of what a field was called
and what a value meant. That produced three failure modes that were all silent
from the brand owner's side:

1. **A column that vanished.** ``materiel`` instead of ``material`` was read by
   nothing and reported by nothing; the product was created without a material
   and the preview said "ready".
2. **Two columns fighting.** A CSV with both ``price`` and ``base_price`` mapped
   onto the same canonical field. Whichever appeared later in the header row won,
   so the price the brand saw in the preview could differ from the price a
   re-ordered export produced — with no warning either time.
3. **A tag that could never match.** ``occasion_tags`` was stored verbatim, but
   the styling engine and the catalogue search match against the canonical
   vocabulary in ``services/wardrobe_taxonomy.py``. A row tagged ``office`` was
   imported, published, and then invisible to every ``Work & Business`` filter
   and to the stylist.

Everything here is pure: no database, no session, no I/O. The importer and the
API call it, which is what makes "the contract" a single thing rather than a
convention that has to be remembered in four places.

The contract is versioned (``CONTRACT_VERSION``) so an import job recorded
months ago can be replayed and interpreted under the rules it was accepted
with.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

CONTRACT_VERSION = "1.0"

# ─────────────────────────────────────────────────────────────────────────────
# Fields a brand may NEVER write
# -----------------------------------------------------------------------------
# These are platform decisions, not catalogue content. A brand that sends one is
# not making an off-by-one mistake, it is asking for a promotion it is not
# entitled to grant itself — so the row is REJECTED with a reason, never quietly
# stripped. Silently dropping `is_featured` would let a brand believe the field
# was accepted and then wonder, months later, why nothing is featured.
#
# Deliberately NOT folded into `is_active` or any moderation flag: being listed
# as featured is an editorial decision about merchandising, while `is_active` is
# publication state. Conflating them means a takedown (is_active=False) would
# also erase a merchandising decision, and a feature request would publish an
# unreviewed product.
ADMIN_ONLY_FIELDS: Dict[str, str] = {
    "is_featured": (
        "featured placement is decided by CONFIT's merchandising team, not by the "
        "brand import"
    ),
    "is_active": (
        "publishing and unpublishing a product is a platform action; imported rows "
        "are published through the normal review path"
    ),
    "moderation_status": (
        "moderation state is set by CONFIT's review process and cannot be written "
        "by an import"
    ),
    "verification_status": (
        "verification is a platform decision and cannot be written by an import"
    ),
    "rating": (
        "ratings are computed from real customer reviews, never imported"
    ),
    "review_count": (
        "review counts are computed from real customer reviews, never imported"
    ),
    "sales_count": (
        "sales counts are computed from real orders, never imported"
    ),
}

#: Header spellings that reach an admin-only field. Checked AFTER alias
#: resolution as well, so ``featured`` or ``is_featured`` are both caught.
ADMIN_ONLY_HEADER_ALIASES: Dict[str, str] = {
    "featured": "is_featured",
    "is_featured": "is_featured",
    "is_active": "is_active",
    "active": "is_active",
    "published": "is_active",
    "moderation_status": "moderation_status",
    "verified": "verification_status",
    "verification_status": "verification_status",
    "rating": "rating",
    "review_count": "review_count",
    "sales_count": "sales_count",
}

# ─────────────────────────────────────────────────────────────────────────────
# Gender: the vocabulary and where the value came from
# -----------------------------------------------------------------------------
# ``services/styling/garment_gender`` understands exactly three values. Anything
# else that reaches the stylist is either ignored (a men's request returns
# women's shoes) or crashes the rules engine, so the importer normalises on the
# way in — and records WHICH of the three routes produced the value, because
# "the brand said unisex" and "we guessed from the title" are different facts
# about a product and the report must not present them identically.
VALID_GENDERS: Tuple[str, ...] = ("mens", "womens", "unisex")

GENDER_SYNONYMS: Dict[str, str] = {
    "men": "mens", "man": "mens", "male": "mens", "mens": "mens", "men's": "mens",
    "men’s": "mens", "menswear": "mens", "menswear ": "mens", "gents": "mens",
    "gentlemen": "mens", "gentlemen's": "mens", "boy": "mens",
    "boys": "mens", "male adult": "mens", "رجالي": "mens", "رجال": "mens",
    "women": "womens", "woman": "womens", "female": "womens", "womens": "womens",
    "women's": "womens", "women’s": "womens", "womenswear": "womens",
    "ladies": "womens", "ladys": "womens", "lady's": "womens", "lady": "womens",
    "girl": "womens", "girls": "womens", "female adult": "womens", "نسائي": "womens",
    "نساء": "womens",
    "unisex": "unisex", "all": "unisex", "any": "unisex", "both": "unisex",
    "none": "unisex", "everyone": "unisex", "gender neutral": "unisex",
    "gender-neutral": "unisex", "للجنسين": "unisex",
}

GENDER_EXPLICIT = "explicit"     # the brand wrote a recognised value
GENDER_INFERRED = "inferred"     # derived from the title/category by the stylist
GENDER_DEFAULTED = "defaulted"   # nothing usable anywhere; fell back to unisex


def normalize_gender(raw: Any) -> Tuple[str, str]:
    """Return ``(gender, provenance)`` for a raw cell value.

    Unrecognised text is NOT coerced into a gender: it raises ``ValueError`` so
    the caller can reject the row and say what it expected. Coercing a typo
    ("womans") to ``unisex`` would publish a product the stylist can never
    recommend to anyone — a wrong answer that looks like a successful import.
    """
    if raw is None:
        return "", ""
    text = str(raw).strip()
    if not text:
        return "", ""
    key = re.sub(r"\s+", " ", text).strip().lower()
    if key in GENDER_SYNONYMS:
        return GENDER_SYNONYMS[key], GENDER_EXPLICIT
    raise ValueError(
        f'Gender "{text}" is not recognised. Use one of '
        + ", ".join(VALID_GENDERS) + " (men/women are also accepted)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Style / occasion: import-time canonicalisation
# -----------------------------------------------------------------------------
# Stored tags are matched by other services, so the importer must write the SAME
# strings those services look for. Without this, an imported product is
# published but unreachable by the filters it was imported for.
TAG_KINDS = ("style", "occasion")

#: Upper bound on tags per field, mirroring the row validator.
MAX_TAGS = 100
MAX_TAG_LENGTH = 100


def _taxonomy():
    """Import lazily: the taxonomy module is large and not needed for CSV-only runs."""
    from backend.app.services import wardrobe_taxonomy

    return wardrobe_taxonomy


def canonical_tags(values: Sequence[str], kind: str) -> Tuple[List[str], List[str]]:
    """Map free-text tags onto the canonical vocabulary.

    Returns ``(canonical, unrecognised)``.

    Unrecognised tags are KEPT, not dropped: a brand may have a genuinely new
    descriptor, and silently deleting their data is worse than storing it. They
    are returned separately so the preview can say plainly that this tag will not
    match CONFIT's filters — which is the difference between "your product is
    hard to find" and "your product is impossible to find, and nobody told you".
    """
    if kind not in TAG_KINDS:
        raise ValueError(f"unknown tag kind {kind!r}")
    taxonomy = _taxonomy()
    canonical: List[str] = []
    unrecognised: List[str] = []

    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        mapped: Optional[str] = None
        if kind == "occasion":
            mapped = _canonical_occasion(taxonomy, text)
        else:
            # Style tags are free-form in CONFIT — there is no controlled
            # vocabulary to canonicalise against, so the brand's own wording is
            # what gets stored (cleaned, never invented).
            cleaned = re.sub(r"[^A-Za-z0-9 \-&']", "", text).strip()
            mapped = cleaned or None

        if mapped:
            if mapped not in canonical:
                canonical.append(mapped)
        else:
            # Preserve the brand's own wording, de-duplicated, so the choice is
            # visible and reversible rather than erased.
            if text not in unrecognised:
                unrecognised.append(text)
            if text not in canonical:
                canonical.append(text)

    return canonical, unrecognised


def _canonical_occasion(taxonomy, text: str) -> Optional[str]:
    """Map one occasion phrase onto ``wardrobe_taxonomy.OCCASIONS``.

    Uses the taxonomy's own alias table, longest alias first (so "smart casual"
    wins over "casual"), and only falls back to its fuzzy matcher when that
    matcher actually returns a candidate. ``normalize_occasions`` is deliberately
    NOT used here: it returns ``["Casual"]`` for input it cannot read, which
    would let the importer invent an occasion the brand never wrote.
    """
    normalised = re.sub(r"\s+", " ", text.strip().lower())
    if not normalised:
        return None
    for alias, target in sorted(
        taxonomy._OCCASION_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if alias in normalised:
            return target
    closest = taxonomy._closest(normalised, taxonomy.OCCASIONS)
    return closest or None


def split_tag_cell(value: Any) -> List[str]:
    """Parse a CSV cell or JSON value into a tag list.

    Accepts a JSON array, a comma-separated string, or an actual list. Raises
    ``ValueError`` for anything that would silently lose data (an object, a
    nested array, an oversized list).
    """
    import json

    if value in (None, ""):
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                value = json.loads(text)
            except ValueError as exc:
                raise ValueError(f"Malformed JSON array: {exc}") from exc
        elif text.startswith("{"):
            # A JSON object in a tag cell is a mapping the importer cannot
            # interpret; storing it would create one long nonsense tag.
            raise ValueError(
                "This looks like a JSON object. Send a list of tags or "
                "comma-separated text."
            )
        else:
            value = [part.strip() for part in text.split(",")]
    if not isinstance(value, list):
        raise ValueError("Must be a list of tags or comma-separated text")
    if len(value) > MAX_TAGS:
        raise ValueError(f"Too many tags (max {MAX_TAGS})")
    for item in value:
        if not isinstance(item, str):
            raise ValueError("Every tag must be text")
        if len(item) > MAX_TAG_LENGTH:
            raise ValueError(f'Tag "{item[:20]}…" is longer than {MAX_TAG_LENGTH} characters')
    return [item for item in value if item.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Header resolution
# ─────────────────────────────────────────────────────────────────────────────

def resolve_headers(
    headers: Iterable[str],
    *,
    aliases: Dict[str, str],
    known: Iterable[str],
) -> Dict[str, Any]:
    """Resolve a header row against the contract.

    Returns::

        {
          "fields":     {original_header: canonical_name | None},
          "unknown":    [original_header, ...],
          "forbidden":  [(original_header, canonical_admin_field, reason), ...],
          "collisions": [(canonical, [header, header, ...]), ...],
        }

    ``collisions`` is the case the old importer could not report: two columns
    that mean the same field. It is a WARNING (the import can proceed by taking
    the first non-empty value) but the brand must be told, because the export
    they will produce next month may order them differently.
    """
    known_set = set(known)
    resolved: Dict[str, Any] = {}
    unknown: List[str] = []
    forbidden: List[Tuple[str, str, str]] = []
    by_canonical: Dict[str, List[str]] = {}

    for header in headers:
        name = (header or "").strip()
        if not name:
            continue
        key = name.lower()
        canonical = aliases.get(key, name if name in known_set else key)
        if canonical in known_set:
            resolved[name] = canonical
            by_canonical.setdefault(canonical, []).append(name)
        elif key in ADMIN_ONLY_HEADER_ALIASES or name in ADMIN_ONLY_FIELDS:
            field = ADMIN_ONLY_HEADER_ALIASES.get(key, name)
            forbidden.append((name, field, ADMIN_ONLY_FIELDS.get(field, "admin-only field")))
            resolved[name] = field
        else:
            resolved[name] = None
            unknown.append(name)

    collisions = [(c, hs) for c, hs in by_canonical.items() if len(hs) > 1]
    return {
        "fields": resolved,
        "unknown": unknown,
        "forbidden": forbidden,
        "collisions": collisions,
    }


def forbidden_field_errors(
    columns: Iterable[str],
    *,
    row_number: int,
    error_factory,
) -> List[Any]:
    """Per-row rejections for admin-only columns.

    ``error_factory(row, field, message, suggestion)`` lets the caller reuse its
    own ``CatalogImportError`` type without this module importing it.
    """
    out = []
    seen = set()
    for column in columns:
        name = (column or "").strip()
        key = name.lower()
        field = ADMIN_ONLY_HEADER_ALIASES.get(key, name if name in ADMIN_ONLY_FIELDS else None)
        if not field or field in seen:
            continue
        seen.add(field)
        out.append(error_factory(
            row_number,
            field,
            f'"{field}" cannot be set by a brand import: '
            + ADMIN_ONLY_FIELDS.get(field, "it is an admin-only field"),
            "Remove the column. Featured placement, publication state and ratings are "
            "managed by CONFIT after review.",
        ))
    return out
