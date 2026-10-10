from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

from backend.app.services.stylist_image_intake import (
    STYLIST_MAX_IMAGES,
    ImageIntakeError,
    parse_images,
)


class GuidedRecommendationConstraints(BaseModel):
    """Structured constraints for the guided first-look contract.

    Palette values are normalized server-side against the catalog colour
    taxonomy. Fit only becomes authoritative when a concrete size profile is
    supplied or present on the authenticated profile; a vague fit preference is
    recorded as preference context but does not create a fake size score.
    """
    palette: Optional[str] = Field(default=None, max_length=40)
    avoid_palette: Optional[str] = Field(default=None, max_length=40)
    preferred_fit: Optional[str] = Field(default=None, max_length=30)
    size_tops: Optional[str] = Field(default=None, max_length=20)
    size_bottoms: Optional[str] = Field(default=None, max_length=20)
    size_shoes: Optional[str] = Field(default=None, max_length=20)


#: ENGINEERING SAFETY DEFAULT — 2000 characters. NOT A PRODUCT REQUIREMENT.
#:
#: Research (2026-09-24): no requirement for a prompt length exists anywhere in the
#: repository — not in the BRD, the API contract checklist, the UX specification or
#: the analytics definitions; the only place the gap is written down is the consumer
#: acceptance report, which records it as an open item. So this bound is an
#: engineering decision, and it is labelled as one.
#:
#: Why a bound at all: the field is `str` with no maximum, the endpoint accepts
#: anonymous callers, and every accepted call spends provider quota and writes a row.
#: A single request could therefore carry an arbitrarily large body — a free
#: amplification path for cost and for the fallback parser, which walks the text.
#:
#: Why 2000: measured against the production database the same day —
#:   stylist_messages: 71 user prompts, p50 53 chars, p95 146, p99 240, MAX 240,
#:   and zero prompts above 1000 characters.
#: 2000 characters is 8.3x the longest prompt any real shopper has sent and ~37x the
#: median, so it cannot truncate observed usage while it still caps the abuse surface
#: (two orders of magnitude below the 4.5 MB serverless request-body ceiling and far
#: below every configured provider's context window, which is not the binding
#: constraint here — cost and abuse are).
#:
#: What a product owner should decide later: whether a hard rejection is the right UX
#: versus truncation with a visible notice, and whether the bound should differ for
#: authenticated users. Until that decision exists, this value is documented as an
#: engineering default, not presented as a product rule.
STYLIST_PROMPT_MAX_CHARS = 2000


STYLIST_HISTORY_MAX_TURNS = 8
STYLIST_HISTORY_TURN_MAX_CHARS = 1200


class StylistHistoryTurn(BaseModel):
    """One EARLIER turn of the chat, sent back so follow-up questions have context.

    Text only. Images are never resent: a photo was analysed once, and its
    result travels in the stored answer, not as raw bytes (FR-008).
    """
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=STYLIST_HISTORY_TURN_MAX_CHARS)


class StylistPromptRequest(BaseModel):
    session_id: Optional[int] = None
    prompt: str = Field(
        min_length=1,
        max_length=STYLIST_PROMPT_MAX_CHARS,
        description=(
            "Natural language request or occasion text e.g. 'I need a smart casual "
            f"outfit for an art gallery opening under $300'. Maximum "
            f"{STYLIST_PROMPT_MAX_CHARS} characters (engineering safety default; "
            "exceeding it is rejected with 422 before any provider call). "
            "Leading/trailing whitespace is trimmed and a whitespace-only prompt is "
            "refused: it is not a request, and answering it would spend a provider "
            "call on nothing."
        ),
    )

    # BEFORE, not after: Pydantic applies min_length/max_length to the raw value
    # first, so an "after" validator means 2000 characters plus padding is refused
    # for the padding. The order is the whole point of a bound expressed in
    # characters the user actually typed.
    @field_validator("prompt", mode="before")
    @classmethod
    def _strip_and_reject_blank(cls, value):
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                raise ValueError("prompt must contain at least one non-whitespace character")
            return trimmed
        return value
    occasion: Optional[str] = None
    budget_limit: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    # Earlier turns of this chat, oldest first. The server keeps only the most
    # recent STYLIST_HISTORY_MAX_TURNS; the latest message is always `prompt`.
    history: Optional[List[StylistHistoryTurn]] = Field(
        default=None, max_length=STYLIST_HISTORY_MAX_TURNS
    )
    voice_input_used: bool = False
    #: Use the shopper's own wardrobe when composing advice (STY-03). Honoured
    #: only for a signed-in shopper who has wardrobe items; the response says
    #: whether it was actually used.
    include_wardrobe_items: bool = True
    recommendation_constraints: Optional[GuidedRecommendationConstraints] = None
    #: Optional outfit / garment photos as ``data:image/(png|jpeg|webp);base64``
    #: URLs (Mode A). Validated here, at the boundary: type by magic bytes, size
    #: capped per image, at most STYLIST_MAX_IMAGES. Never persisted.
    images: List[str] = Field(default_factory=list, max_length=STYLIST_MAX_IMAGES)

    @field_validator("images", mode="after")
    @classmethod
    def _validate_images(cls, value: List[str]) -> List[str]:
        try:
            parse_images(value)
        except ImageIntakeError as exc:
            raise ValueError(str(exc)) from None
        return value

    @property
    def mode(self) -> str:
        """``A`` when images are attached (multi-image styling), else ``B``."""
        return "A" if self.images else "B"


class OutfitItemOut(BaseModel):
    id: int
    product_id: int
    product_title: str
    brand_name: str
    category_name: str
    price: float
    #: Real catalogue currency of this item (e.g. "EGP"). None on legacy
    #: persisted messages — clients must render an honest placeholder, never
    #: assume a currency.
    currency: Optional[str] = None
    image_url: str
    color_hex: str
    position: str  # "top", "bottom", "outerwear", "shoes", "footwear", "accessory", "dress"
    slot_type: Optional[str] = None
    color_family: Optional[str] = None
    material: Optional[str] = None
    role_in_outfit: Optional[str] = None
    sku_id: Optional[int] = None
    selected_size: Optional[str] = "M"

    model_config = ConfigDict(from_attributes=True)


class OutfitOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    occasion: str
    total_price: float
    #: Currency of total_price, from the composed items themselves.
    currency: Optional[str] = None
    compatibility_score: int
    color_palette: List[str]
    style_tags: List[str]
    is_saved: bool
    is_system_curated: bool
    is_complete: Optional[bool] = True
    completeness_status: Optional[str] = "complete_look"
    completeness_label: Optional[str] = "Complete Look"
    missing_slots: Optional[List[str]] = []
    color_harmony_score: Optional[int] = 95
    formality_score: Optional[int] = 90
    budget_limit: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    within_budget: Optional[bool] = True
    budget_note: Optional[str] = None
    items: List[OutfitItemOut]
    created_at: datetime
    updated_at: Optional[datetime] = None
    composition_warnings: Optional[List[str]] = []
    # Sharing state is reported from the real token lifecycle (OUTFIT-01).
    is_shared: Optional[bool] = False
    share_url: Optional[str] = None
    share_expires_at: Optional[datetime] = None
    share_view_count: Optional[int] = 0
    #: Owned wardrobe items that pair with this look (STY-03). Present only when
    #: the shopper asked for wardrobe grounding and it was actually used.
    wardrobe_pairings: Optional[List[Dict[str, Any]]] = None
    #: Colour coordination of this look against the colours extracted from the
    #: shopper's images (Mode A). None for text-only turns.
    color_coordination: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class StylistMessageOut(BaseModel):
    id: int
    session_id: int
    sender: str
    content: str
    audio_url: Optional[str] = None
    intent_detected: Dict[str, Any]
    recommendations: List[OutfitOut]
    created_at: datetime
    #: Which engine produced this answer. A provider call yields
    #: "<Provider> <model actually served>"; a total provider failure yields
    #: "CONFIT Grounded Styling Engine" (deterministic, catalogue-grounded);
    #: "none" means no provider was called (clarifying question). Without this
    #: the client cannot tell generated advice from fallback prose — see the
    #: comment in stylist_service.interact_with_stylist.
    engine: Optional[str] = None
    #: "A" (images analysed) or "B" (text-only). Additive; absent on old rows.
    mode: Optional[str] = None
    #: Set when Mode A was requested but ran as Mode B. Shopper-safe reason.
    fallback_reason: Optional[str] = None
    #: What the image analysis produced (colours, garments, engine). Never the
    #: image bytes. None for text-only turns.
    image_analysis: Optional[Dict[str, Any]] = None
    #: WHY this text is what it is. "provider": a model answered and passed the
    #: grounding check. "grounding_rejected": a model answered but named a brand
    #: the shopper was not offered, so the grounded template was used instead.
    #: "providers_unavailable": every available provider leg failed.
    #: "no_provider_configured": no provider leg was available. None on
    #: clarifying questions and for rows saved before this field existed.
    answer_source: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StylistSessionOut(BaseModel):
    id: int
    user_id: int
    session_title: str
    messages: List[StylistMessageOut]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OutfitCreateInput(BaseModel):
    """Canonical outfit-creation contract.

    The client may reference items EITHER by SKU (`product_sku_ids`) or by
    product (`product_ids`); at least one must be non-empty. The service layer
    resolves product ids -> a default in-stock SKU so both the Outfit Builder
    (SKU-based canvas) and the Stylist cards (product-based) share one contract.
    """
    title: str = Field(min_length=1, max_length=255)
    occasion: str = Field(default="Casual", max_length=100)
    product_sku_ids: Optional[List[int]] = None
    product_ids: Optional[List[int]] = None
    description: Optional[str] = Field(default=None, max_length=2000)


class OutfitUpdateInput(BaseModel):
    """Explicit, allow-listed update schema (no mass-assignment).

    Only client-editable fields are accepted. Protected fields (user_id,
    compatibility_score, is_saved, share_token, system metadata) cannot be
    set through this endpoint.
    """
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    occasion: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)


class OutfitItemsReplaceInput(BaseModel):
    """Full replacement of a saved look's item set (canvas edit / reorder).

    Deliberately a PUT-style whole-set contract rather than per-item patches:
    the composition policy validates a *set*, so partial mutations could never
    be checked coherently, and a whole-set swap is idempotent under retry.
    """
    product_sku_ids: Optional[List[int]] = Field(default=None, max_length=12)
    product_ids: Optional[List[int]] = Field(default=None, max_length=12)


class CompositionPreviewInput(BaseModel):
    """Dry-run input for the live canvas validity check."""
    product_sku_ids: Optional[List[int]] = Field(default=None, max_length=12)
    product_ids: Optional[List[int]] = Field(default=None, max_length=12)


class CompositionViolationOut(BaseModel):
    code: str
    message: str
    positions: List[str] = []


class CompositionVerdictOut(BaseModel):
    """Explainable validity verdict — the UI shows the reason, not a guess."""
    is_valid: bool
    violations: List[CompositionViolationOut] = []
    warnings: List[str] = []
    missing_positions: List[str] = []
    resolved_items: List[Dict[str, Any]] = []
    unresolved_ids: List[int] = []


class ShareRequestInput(BaseModel):
    """Options when minting a share link."""
    ttl_days: Optional[int] = Field(default=None, ge=1, le=365)
    rotate: bool = False


class ShareLinkOut(BaseModel):
    """Truthful share-link state. ``is_active`` is computed from revocation +
    expiry, never assumed from the mere existence of a token."""
    outfit_id: int
    share_token: Optional[str] = None
    share_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    view_count: int = 0


class ShareRevokeOut(BaseModel):
    outfit_id: int
    revoked: bool
    was_active: bool
    is_active: bool


class PublicLookItemOut(BaseModel):
    """A single item on a publicly shared look — catalog facts only."""
    product_title: str
    brand_name: str
    category_name: str
    price: float
    image_url: str
    color_hex: str
    position: str


class PublicLookOut(BaseModel):
    """Public, read-only shared-look DTO (C8).

    Deliberately excludes every private field: no outfit id, no user_id, no
    owner identity, no profile data, no internal metadata.
    """
    title: str
    occasion: str
    description: Optional[str]
    total_price: float
    compatibility_score: int
    items: List[PublicLookItemOut]
    created_at: datetime


class CompatibilityCheckRequest(BaseModel):
    product_ids: List[int]
    target_occasion: Optional[str] = "Casual"


class CompatibilityCheckResponse(BaseModel):
    compatibility_score: int  # 0-100
    color_harmony_type: str   # "Monochromatic", "Complementary", "Analogous", "Triadic", "Balanced Neutral"
    color_harmony_verdict: str
    aesthetic_consistency_verdict: str
    occasion_score: int
    budget_status: str
    suggestions: List[str]
    # ── Feature 06 (additive; defaults keep every pre-06 client green) ──
    # engine names WHO produced compatibility_score: the OutfitTransformer
    # model (Modal CPU worker) or the deterministic rules heuristic. The
    # shopper must never mistake one for the other.
    engine: Optional[str] = None                 # "outfit_transformer_clip" | "rules_heuristic"
    model_detail: Optional[Dict[str, Any]] = None  # worker's type_aware + aesthetic_axes + disclosures
    compatibility_source: Optional[str] = None   # "model" | "heuristic"
    compatibility_available: Optional[bool] = None  # False + reason when the model path was unavailable
    reason: Optional[str] = None                 # honest reason the model path was skipped


class FillInTheBlankRequest(BaseModel):
    """Complete a partial outfit from the catalog.

    product_ids: the items the shopper already has (>=1).
    target_slot: coarse layering slot to complete ("footwear", "lower", …);
        optional — without it the model free-completes.
    candidate_product_ids: optional explicit candidate pool; by default a
        bounded catalog sweep filtered to the target slot.
    """
    product_ids: List[int]
    target_slot: Optional[str] = None
    candidate_product_ids: Optional[List[int]] = None
    top_k: int = 5

    @field_validator("top_k")
    @classmethod
    def _top_k_range(cls, v: int) -> int:
        if not 1 <= v <= 20:
            raise ValueError("top_k must be 1-20")
        return v


class FillInTheBlankCandidateOut(BaseModel):
    """One ranked completion: a REAL catalog product with the model's
    similarity score. Nothing is invented — id/similarity come verbatim
    from the complementary model's cosine ranking."""
    product_id: int
    rank: int
    similarity: float
    title: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None


class FillInTheBlankResponse(BaseModel):
    fitb_available: bool
    engine: Optional[str] = None        # "outfit_transformer_clip" | "rules_heuristic" | None
    reason: Optional[str] = None        # honest reason when unavailable
    target_slot: Optional[str] = None
    target_category_used: Optional[str] = None
    outfit_product_ids: List[int] = []
    ranked: List[FillInTheBlankCandidateOut] = []
    method_note: Optional[str] = None
