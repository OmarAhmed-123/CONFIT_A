"""Wardrobe outfit recommendation — IBM Granite stylist tutorial, productised.

Flow (mirrors the tutorial's step 8, hardened):

1. Load the caller's READY wardrobe items (soft-deleted and still-processing
   items are never styled).
2. Reduce them to model-safe closet records keyed by ``wardrobe_item_id``.
3. Ask the configured watsonx.ai reasoning model (Granite by default) for ONE
   structured outfit, using the version-controlled system prompt.
4. Parse + validate: strict JSON, every referenced id must exist in the
   wardrobe, no duplicates, excluded ids dropped, role sanity-checked
   against the item's real category. Invalid references are *rejected and
   reported*, never resolved by fuzzy matching.
5. Resolve image URLs from the trusted wardrobe rows (never from model text).
6. If the model tier is unavailable/unparseable and the mode allows it,
   return the deterministic wardrobe-first scorer's pick, clearly labelled
   ``source="deterministic_fallback"``, ``ai_generated=False``.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import FeatureNotConfiguredError, ProviderIntegrationError, ValidationDomainError
from backend.app.core.logging import logger
from backend.app.providers.watsonx import client as _client_mod
from backend.app.providers.watsonx.client import WatsonxClient, WatsonxError, watsonx_configured
from backend.app.providers.watsonx.prompts import (
    STYLIST_PROMPT_VERSION,
    STYLIST_SYSTEM_PROMPT,
    build_stylist_user_message,
)
from backend.app.providers.watsonx.vision import parse_vision_json
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.schemas.wardrobe_stylist import OutfitRecommendation, OutfitRecommendationRequest, RecommendedItem
from backend.app.services import wardrobe_taxonomy as taxonomy
from backend.app.services.storage_service import storage_public_url

CATEGORY_TO_ROLE = {
    "Tops": "top", "Bottoms": "bottom", "Dresses": "dress",
    "Footwear": "footwear", "Outerwear": "outerwear", "Accessories": "accessory",
}
ROLE_TO_CATEGORY = {v: k for k, v in CATEGORY_TO_ROLE.items()}
CORE_ROLES = ("top", "bottom", "footwear")
MAX_CLOSET_ITEMS = 60  # prompt-size guard; newest items first beyond this

# Rule-based fallback copy. Added 2026-10-27 after the quality evaluation showed
# the fallback answered Arabic requests in English (3/3 Arabic scenarios).
_FALLBACK_TEXT = {
    "en": {
        "title": "{occasion} from your wardrobe",
        "summary": "Pieces chosen by occasion tags, season, favourites and neutral colours. "
                   "Configure watsonx.ai for a reasoned, context-specific recommendation.",
        "fallback_notice": "This outfit was assembled by CONFIT's rule-based matcher, not by the AI stylist "
                           "(the language model was unavailable). Reasons are generic.",
        "missing": "No {category} in your wardrobe to complete this look.",
        "no_occasion_match": "Nothing in your wardrobe is tagged for {occasion}; this is the closest match, not a fit.",
        "unsuitable_summary": "Your wardrobe has no items suited to {occasion}. The pieces below are the closest available, "
                              "shown so you can see what you own — they are not a recommended outfit for this.",
        "partial_summary": "Only some of these pieces are tagged for {occasion}; treat this as a partial match.",
        "filtered_summary": "Final selection: {items}. Pieces in colours you asked to avoid were left out, "
                            "so this look is {state}.",
        "incomplete_word": "incomplete",
        "complete_word": "complete",
        "neutral_reason": "Closest available {category}; not tagged for {occasion}.",
        "unfilled": "No {category} left once the colours you asked to avoid were excluded.",
        "role_collision": "{n} suggested piece(s) duplicated a position already filled and were left out; "
                          "the stylist may have mixed up item ids.",
        "reason_mismatch": "{n} explanation(s) described a different garment than the one referenced and were replaced "
                           "with a rule-based note.",
        "completed_by_rules": "{n} piece(s) were added by CONFIT's rule-based matcher to complete the look; "
                              "they were not chosen by the AI stylist.",
        "generic_reason": "Selected for your {occasion} request.",
        "r_tagged": "tagged for {occasion}", "r_season": "suits {season}", "r_favourite": "one of your favourites",
        "r_neutral": "{color} pairs easily", "r_best_available": "{title}: best available {role} for this request.",
    },
    "ar": {
        "title": "إطلالة {occasion} من خزانتك",
        "summary": "قطع اختيرت وفق وسوم المناسبة والموسم والمفضّلات والألوان المحايدة. "
                   "فعّل watsonx.ai للحصول على توصية مُعلَّلة ومناسبة للسياق.",
        "fallback_notice": "جُمعت هذه الإطلالة بواسطة المُطابِق القاعدي في CONFIT وليس بواسطة المصمم الذكي "
                           "(النموذج اللغوي غير متاح). الأسباب عامة.",
        "missing": "لا يوجد {category} في خزانتك لإكمال هذه الإطلالة.",
        "no_occasion_match": "لا توجد قطعة في خزانتك موسومة لمناسبة {occasion}؛ هذه أقرب مطابقة وليست ملائمة تمامًا.",
        "unsuitable_summary": "لا تحتوي خزانتك على قطع مناسبة لـ {occasion}. القطع أدناه هي الأقرب المتاح، "
                              "معروضة لترى ما تملك — وليست إطلالة موصى بها لهذه المناسبة.",
        "partial_summary": "بعض هذه القطع فقط موسومة لـ {occasion}؛ اعتبرها مطابقة جزئية.",
        "filtered_summary": "الاختيار النهائي: {items}. استُبعدت القطع بالألوان التي طلبت تجنّبها، "
                            "لذا هذه الإطلالة {state}.",
        "incomplete_word": "غير مكتملة",
        "complete_word": "مكتملة",
        "neutral_reason": "أقرب {category} متاح؛ غير موسوم لـ {occasion}.",
        "unfilled": "لم يتبقَّ {category} بعد استبعاد الألوان التي طلبت تجنّبها.",
        "role_collision": "استُبعدت {n} قطعة مقترحة لأنها تكرر موضعًا مشغولًا؛ ربما خلط المصمم بين معرّفات القطع.",
        "reason_mismatch": "استُبدل {n} تفسير لأنه وصف قطعة مختلفة عن القطعة المُشار إليها، ووُضع بدلًا منه تعليق قاعدي.",
        "completed_by_rules": "أُضيفت {n} قطعة بواسطة المُطابِق القاعدي في CONFIT لإكمال الإطلالة؛ لم يخترها المصمم الذكي.",
        "generic_reason": "اختيرت لطلبك الخاص بـ {occasion}.",
        "r_tagged": "موسومة لمناسبة {occasion}", "r_season": "مناسبة لفصل {season}", "r_favourite": "من مفضّلاتك",
        "r_neutral": "اللون {color} سهل التنسيق", "r_best_available": "{title}: أفضل {role} متاح لهذا الطلب.",
    },
}
_CATEGORY_AR = {"Tops": "قطعة علوية", "Bottoms": "قطعة سفلية", "Dresses": "فستان", "Footwear": "حذاء",
                "Outerwear": "قطعة خارجية", "Accessories": "إكسسوار"}
_ROLE_AR = {"top": "قطعة علوية", "bottom": "قطعة سفلية", "dress": "فستان", "footwear": "حذاء",
            "outerwear": "قطعة خارجية", "accessory": "إكسسوار"}
_SEASON_AR = {"spring": "الربيع", "summer": "الصيف", "autumn": "الخريف", "winter": "الشتاء"}
_OCCASION_AR = {
    "casual": "كاجوال", "smart casual": "سمارت كاجوال", "work & business": "العمل", "business": "العمل",
    "business formal": "العمل الرسمي", "cocktail": "الكوكتيل", "formal": "المناسبات الرسمية",
    "black tie": "البدلة الرسمية (بلاك تاي)", "active": "النشاط الرياضي", "lounge": "الاسترخاء المنزلي",
    "evening": "السهرة", "interview": "مقابلة العمل", "wedding": "حفل الزفاف", "gym": "التمرين",
}


def _occasion_label(value: Optional[str], language: str) -> str:
    """Occasion/activity for prose: Arabic label when known (keeps Arabic prose free of
    English enum values), otherwise the user's own words."""
    text = (value or "").strip()
    if language == "ar":
        return _OCCASION_AR.get(text.lower(), text)
    return text
_COLOR_AR = {"Black": "الأسود", "White": "الأبيض", "Navy": "الكحلي", "Beige": "البيج", "Grey": "الرمادي", "Ivory": "العاجي"}


def _loads(text: Optional[str]) -> List[Any]:
    try:
        v = json.loads(text) if text else []
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


class WardrobeStylistService:
    def __init__(self, db: Session, client: Optional[WatsonxClient] = None):
        self.db = db
        self.wardrobe_repo = WardrobeRepository(db)
        self._client = client

    # ── public ───────────────────────────────────────────────────────
    def closet_for_user(self, user_id: int) -> List[Any]:
        return [
            it for it in self.wardrobe_repo.get_user_items(user_id)
            if (getattr(it, "processing_status", "ready") or "ready") == "ready"
        ]

    def _release_db_connection(self, items: List[Any]) -> None:
        """Give the pooled connection back BEFORE awaiting the model.

        Measured 2026-10-27 (PostgreSQL 17, 2 uvicorn workers, 20 VU, 5 s model
        double): the request session stayed "idle in transaction" for the whole
        model call, pinning 15 connections (= pool_size 5 + max_overflow 10 of
        one worker) so unrelated fast endpoints queued on the pool
        (GET /wardrobe/outfits max 3.2 s vs 8 ms idle; save_outfit p95 1.55 s
        at 20 VU vs 0.03 s at 10 VU). Everything this service needs from the
        rows is already loaded as plain columns (no relationships are
        touched), so the objects are detached first — rollback() would
        otherwise expire them and the next attribute read would silently
        re-open a connection.
        """
        try:
            for it in items:
                self.db.expunge(it)
            self.db.rollback()
        except Exception as exc:  # pragma: no cover - defensive, never break a request
            logger.warn("wardrobe_stylist_release_connection_failed", error=str(exc)[:120])

    async def recommend(self, user_id: int, req: OutfitRecommendationRequest) -> OutfitRecommendation:
        items = self.closet_for_user(user_id)
        self._release_db_connection(items)
        excluded = set(req.excluded_item_ids)
        usable = [it for it in items if it.id not in excluded]
        if not usable:
            raise ValidationDomainError(
                "Your wardrobe has no analysed items to style yet. Upload a few pieces "
                "(a top, a bottom and footwear is a good start) and try again."
            )

        mode = (settings.WARDROBE_STYLIST_PROVIDER or "auto").lower()
        if mode not in ("auto", "watsonx", "deterministic"):
            mode = "auto"
        context = self._context(req)

        if mode in ("auto", "watsonx"):
            client = self._client or _client_mod.get_watsonx_client()
            if client.configured:
                try:
                    return await self._recommend_with_model(client, usable, req, context)
                except ProviderIntegrationError as exc:
                    if mode == "watsonx":
                        raise
                    logger.warn("wardrobe_stylist_model_degraded", reason=str(exc)[:160])
                    return self._deterministic(usable, req, context, fallback_reason=str(exc)[:200])
            if mode == "watsonx":
                raise FeatureNotConfiguredError(
                    "watsonx_stylist",
                    "The AI stylist is not configured: set WATSONX_APIKEY, WATSONX_PROJECT_ID and WATSONX_URL.",
                )
            return self._deterministic(usable, req, context, fallback_reason="watsonx_not_configured")
        return self._deterministic(usable, req, context, fallback_reason="provider_mode_deterministic")

    def status(self, user_id: int) -> Dict[str, Any]:
        ready = self.closet_for_user(user_id)
        cats = sorted({taxonomy.normalize_category(it.category) for it in ready})
        return {
            "watsonx_configured": watsonx_configured(),
            "watsonx_url": settings.WATSONX_URL if watsonx_configured() else None,
            "vision_model_id": settings.WATSONX_VISION_MODEL_ID if watsonx_configured() else None,
            "reasoning_model_id": settings.WATSONX_REASONING_MODEL_ID if watsonx_configured() else None,
            "vision_provider_mode": settings.WARDROBE_VISION_PROVIDER,
            "stylist_provider_mode": settings.WARDROBE_STYLIST_PROVIDER,
            "legacy_vision_configured": bool(settings.GEMINI_API_KEY or settings.NVIDIA_API_KEY),
            "ready_items": len(ready),
            "categories_present": cats,
            "prompt_version": STYLIST_PROMPT_VERSION,
        }

    # ── model path ───────────────────────────────────────────────────
    async def _recommend_with_model(
        self, client: WatsonxClient, items: List[Any], req: OutfitRecommendationRequest, context: Dict[str, Any]
    ) -> OutfitRecommendation:
        closet = [self._closet_record(it) for it in items[:MAX_CLOSET_ITEMS]]
        messages = [
            {"role": "system", "content": STYLIST_SYSTEM_PROMPT},
            {"role": "user", "content": build_stylist_user_message(closet, context)},
        ]
        try:
            result = await client.chat(
                model_id=settings.WATSONX_REASONING_MODEL_ID, messages=messages,
                max_tokens=900, temperature=0.2, response_json=True,
                deployment_id=settings.WATSONX_REASONING_DEPLOYMENT_ID or None,
            )
        except WatsonxError as exc:
            raise ProviderIntegrationError("watsonx", exc.code, retryable=exc.retryable) from exc

        try:
            raw = parse_vision_json(result.content)
        except ValueError as exc:
            logger.warn("wardrobe_stylist_malformed_output", model_id=result.model_id, sample=result.content[:160])
            raise ProviderIntegrationError("watsonx", f"model returned malformed JSON ({exc})", retryable=True) from exc

        self._dropped_items = []
        picked, rejected, limitations = self._validate_selection(raw, items, req)
        dropped = list(self._dropped_items)
        if not picked:
            raise ProviderIntegrationError(
                "watsonx", "model did not reference any valid wardrobe item", retryable=True
            )

        completed = self._complete_core_positions(picked, items, req)
        if completed:
            picked.extend(completed)
            # The model may have written "no suitable footwear in the wardrobe" for a
            # position the server has just filled — drop those claims (contradiction).
            filled_words = {w for c in completed for w in self._ROLE_WORDS.get(c.role, ())}
            limitations = [lim for lim in limitations if not any(w in lim.lower() for w in filled_words)]
            limitations.append(
                _FALLBACK_TEXT["ar" if req.language == "ar" else "en"]["completed_by_rules"].format(n=len(completed))
            )
        present_roles = {p.role for p in picked}
        missing = self._missing_categories(items, present_roles)
        for m in missing:
            note = f"No {m.lower()} in your wardrobe to complete this look."
            if note not in limitations:
                limitations.append(note)
        model_missing = [str(x) for x in (raw.get("missing_categories") or []) if isinstance(x, str)]
        for m in model_missing:
            cat = taxonomy.normalize_category(m)
            if cat not in missing and cat not in {ROLE_TO_CATEGORY[r] for r in present_roles}:
                missing.append(cat)

        by_id = {it.id: it for it in items}
        is_complete = self._is_complete(present_roles)
        summary, notes, assumptions, limitations, fit = self._reconcile(
            req=req, picked=picked, picked_items=[by_id[p.wardrobe_item_id] for p in picked], dropped=dropped,
            summary=self._str(raw.get("summary"), 600) or "A coordinated outfit from your wardrobe.",
            styling_notes=self._str_list(raw.get("styling_notes"), 4, 240),
            assumptions=self._str_list(raw.get("assumptions"), 4, 200),
            limitations=limitations, is_complete=is_complete,
        )
        return OutfitRecommendation(
            outfit_id=f"wx_{uuid.uuid4().hex[:12]}",
            occasion=req.occasion,
            title=self._str(raw.get("title"), 80) or f"{req.occasion} look",
            summary=summary,
            items=picked,
            styling_notes=notes,
            limitations=limitations[:6],
            missing_categories=missing,
            assumptions=assumptions,
            is_complete=is_complete,
            fit_status=fit,
            source="watsonx",
            ai_generated=True,
            model_id=result.model_id,
            prompt_version=STYLIST_PROMPT_VERSION,
            latency_seconds=result.latency_seconds,
            rejected_references=rejected,
            context=context,
        )

    # ── colour constraints (enforced, not just prompted) ─────────────
    _NEGATION_WORDS = ("no", "not", "without", "avoid", "never", "except", "لا", "بدون", "بلا", "ليس", "تجنب", "ماعدا", "ما عدا")

    @staticmethod
    def _known_color_family(text: str) -> Optional[str]:
        """normalize_color() falls back to "Black" for unknown words, which is
        fine for labelling but dangerous for a ban list. Only map strings that
        actually contain a known alias."""
        v = taxonomy._norm(text)
        if not v:
            return None
        fam = taxonomy.normalize_color(v)
        if any(alias in v for alias in taxonomy.COLOR_FAMILIES.get(fam, [])):
            return fam
        return None

    @classmethod
    def banned_color_families(cls, req: OutfitRecommendationRequest) -> set:
        """Colour families the answer must not contain.

        Sources: the explicit ``excluded_colors`` list, plus colour words in
        the free-text ``exclusions`` field when they follow a negation word
        ("no black", "without white", "بدون أسود"). The free-text parse is
        deliberately narrow so "white sneakers are fine" does not ban white.
        Added 2026-10-27: until then exclusions reached the model as prose and
        were never checked on the way back.
        """
        banned: set = set()
        for c in req.excluded_colors:
            fam = cls._known_color_family(c)
            if fam:
                banned.add(fam)
        text = taxonomy._norm(req.exclusions or "")
        if text:
            words = re.split(r"[\s,;،/]+", text)
            for i, w in enumerate(words):
                if w in cls._NEGATION_WORDS:
                    for nxt in words[i + 1 : i + 3]:
                        fam = cls._known_color_family(nxt)
                        if fam and any(nxt == alias or nxt in alias.split() for alias in taxonomy.COLOR_FAMILIES[fam]):
                            banned.add(fam)
        return banned

    @classmethod
    def unrecognised_excluded_colors(cls, req: OutfitRecommendationRequest) -> List[str]:
        return [c for c in req.excluded_colors if cls._known_color_family(c) is None]

    @classmethod
    def _unrecognised_limitation(cls, req: OutfitRecommendationRequest) -> List[str]:
        unknown = cls.unrecognised_excluded_colors(req)
        if not unknown:
            return []
        shown = ", ".join(u[:30] for u in unknown[:3])
        if req.language == "ar":
            return [f"لم نتعرّف على «{shown}» كلون، لذا لم يُطبَّق استبعاد تلقائي له."]
        return [f"'{shown}' was not recognised as a colour, so no automatic exclusion was applied for it."]

    @staticmethod
    def _color_limitation(dropped: int, banned: set, language: str) -> str:
        names = ", ".join(sorted(banned))
        if language == "ar":
            return f"تم استبعاد {dropped} قطعة لأنها بلون طلبتَ تجنّبه ({names})."
        return f"{dropped} piece(s) were left out because they are in a colour you asked to avoid ({names})."

    def _validate_selection(
        self, raw: Dict[str, Any], items: List[Any], req: OutfitRecommendationRequest
    ) -> Tuple[List[RecommendedItem], List[int], List[str]]:
        """The only place model-chosen ids become real items. Unknown ids,
        duplicates, excluded ids, banned colours and role/category mismatches
        are dropped and reported (FR-09, Scenario G)."""
        by_id = {it.id: it for it in items}
        picked: List[RecommendedItem] = []
        rejected: List[int] = []
        limitations: List[str] = []
        seen_ids: set = set()
        seen_roles: set = set()
        banned = self.banned_color_families(req)
        colour_dropped = 0
        dropped: List[Any] = []  # real items the server removed (D10: prose must not describe them)
        role_collisions = 0
        id_mismatches = 0
        for entry in (raw.get("items") or [])[:8]:
            if not isinstance(entry, dict):
                continue
            try:
                item_id = int(entry.get("wardrobe_item_id"))
            except (TypeError, ValueError):
                continue
            it = by_id.get(item_id)
            if it is None or item_id in req.excluded_item_ids:
                rejected.append(item_id)
                continue
            if item_id in seen_ids:
                continue
            if banned and taxonomy.normalize_color(it.color_name) in banned:
                colour_dropped += 1
                dropped.append(it)
                logger.info("wardrobe_stylist_banned_colour_dropped", item_id=item_id)
                continue
            real_role = CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category), "accessory")
            claimed = str(entry.get("role") or "").strip().lower()
            if claimed != real_role:
                # Trust the stored (user-correctable) category, not the model.
                logger.info("wardrobe_stylist_role_corrected", item_id=item_id, claimed=claimed, real=real_role)
            if real_role in seen_roles and real_role != "accessory":
                role_collisions += 1  # one piece per position (D12: often an id/description mix-up)
                continue
            if real_role == "dress" and {"top", "bottom"} & seen_roles:
                role_collisions += 1
                continue
            if real_role in ("top", "bottom") and "dress" in seen_roles:
                role_collisions += 1
                continue
            reason = self._str(entry.get("reason"), 400) or f"Selected for a {req.occasion.lower()} setting."
            # D12: a reason that describes a DIFFERENT wardrobe item (e.g. "dark wash
            # jeans…" attached to the tee's id) must never be shown next to this item.
            others = [o for o in items if o.id != it.id]
            if claimed != real_role and self._mentions_any(reason, others, kept=[it]):
                logger.info("wardrobe_stylist_reason_item_mismatch", item_id=item_id, claimed=claimed, real=real_role)
                reason = self._rule_reason(it, real_role, req)
                id_mismatches += 1
            picked.append(RecommendedItem(
                wardrobe_item_id=it.id, role=real_role,
                category=taxonomy.normalize_category(it.category), title=it.title,
                subcategory=it.subcategory, color_name=it.color_name, color_hex=it.color_hex or "#000000",
                image_url=storage_public_url(it.image_url), reason=reason,
                analysis_source=getattr(it, "analysis_source", None),
                ai_confidence=getattr(it, "ai_confidence", None),
            ))
            seen_ids.add(item_id)
            seen_roles.add(real_role)
        if rejected:
            limitations.append(
                f"{len(rejected)} suggested reference(s) did not match your wardrobe and were discarded."
            )
        if colour_dropped:
            limitations.append(self._color_limitation(colour_dropped, banned, req.language))
        t = _FALLBACK_TEXT["ar" if req.language == "ar" else "en"]
        if role_collisions:
            limitations.append(t["role_collision"].format(n=role_collisions))
        if id_mismatches:
            limitations.append(t["reason_mismatch"].format(n=id_mismatches))
        limitations.extend(self._unrecognised_limitation(req))
        for lim in self._str_list(raw.get("limitations"), 4, 240):
            if lim not in limitations and not self._mentions_any(lim, dropped, kept=[by_id[p.wardrobe_item_id] for p in picked]):
                limitations.append(lim)
        self._dropped_items = dropped
        return picked, rejected, limitations

    # Words a model limitation uses when it claims a position cannot be filled.
    _ROLE_WORDS = {
        "top": ("top", "shirt", "blouse", "قطعة علوية", "قميص", "بلوزة"),
        "bottom": ("bottom", "trouser", "pants", "skirt", "jeans", "بنطلون", "تنورة", "قطعة سفلية"),
        "footwear": ("footwear", "shoe", "heel", "boot", "sneaker", "loafer", "sandal", "حذاء", "أحذية", "كعب"),
        "dress": ("dress", "فستان"),
    }

    # ── D10/D11: reconcile model prose with the final, server-filtered outfit ──
    _GENERIC_TOKENS = frozenset({
        "with", "from", "that", "this", "your", "item", "piece", "look", "colour", "color",
    })

    _AR_PREFIX_RE = re.compile(r"^(?:و|ف|ب|ل|ك)?(?:ال|لل)")

    @classmethod
    def _tokens(cls, text: str) -> set:
        out = set()
        for w in re.findall(r"[\w\u0600-\u06FF]+", (text or "").lower()):
            # Arabic: strip clitic prefixes (و/ب/ل + definite article) and the
            # feminine ta-marbuta/ha so "البلوزة" ≡ "بلوزة"; then apply the length gate.
            if re.search(r"[\u0600-\u06FF]", w):
                w = cls._AR_PREFIX_RE.sub("", w).rstrip("ةه")
                if len(w) >= 3:
                    out.add(w)
            elif len(w) >= 4 and w not in cls._GENERIC_TOKENS:
                out.add(w)
        return out

    @classmethod
    def _mentions_any(cls, text: str, items: List[Any], kept: Optional[List[Any]] = None) -> bool:
        """True when `text` describes one of `items`: the full title, two of its
        title/colour tokens, or ONE token that no kept item shares (e.g. the Arabic
        head noun "بلوزة" when the kept pieces are trousers and shoes). Deterministic;
        used to scrub prose that refers to garments the server removed."""
        low = (text or "").lower()
        text_toks = cls._tokens(low)
        kept_toks: set = set()
        for k in kept or []:
            kept_toks |= cls._tokens(f"{getattr(k, 'title', '')} {getattr(k, 'color_name', '')} {getattr(k, 'subcategory', '')}")
        for it in items:
            title = (it.title or "").strip().lower()
            if title and title in low:
                return True
            toks = cls._tokens(f"{it.title or ''} {it.color_name or ''} {it.subcategory or ''}")
            hit = toks & text_toks
            if len(hit) >= 2 or (hit - kept_toks - cls._COLOUR_WORDS):
                return True
        return False

    _COLOUR_WORDS = frozenset({
        "black", "white", "navy", "grey", "gray", "blue", "brown", "beige", "green", "red", "pink", "tan",
        "ivory", "cream", "camel", "olive", "silver", "gold", "yellow", "orange", "purple", "multi",
        "أسود", "أبيض", "كحلي", "رمادي", "أزرق", "بني", "بيج", "أخضر", "أحمر", "وردي", "ذهبي", "فضي", "سوداء", "بيضاء",
    })

    # Performance/fabric properties the model cannot know from wardrobe metadata.
    _UNSUPPORTED_CLAIM_RE = re.compile(
        r"wick|sweat|moisture|breathab|athletic|cushion|stretch|performance|quick[- ]dry|"
        r"gym[- ]ready|workout|sporty|flexib|يمتص العرق|مقاوم للعرق|رياضي|مرن|مريح للتمارين",
        re.IGNORECASE,
    )

    @staticmethod
    def _item_matches_occasion(it: Any, needles: List[str]) -> bool:
        tags = [str(o).lower() for o in _loads(getattr(it, "occasions", None))]
        tags += [str(t).lower() for t in _loads(getattr(it, "style_tags", None))]
        return any(n and (n in tag or tag in n) for tag in tags for n in needles)

    def _fit_status(self, picked_items: List[Any], req: OutfitRecommendationRequest) -> str:
        """suitable: every piece is tagged for the occasion/activity; partial: some;
        unsuitable: none. Tags come from the user's own wardrobe records (vision
        output or manual edits) — the only evidence the server has."""
        needles = [req.occasion.strip().lower()]
        if getattr(req, "activity", None):
            needles += [w for w in req.activity.strip().lower().split() if len(w) >= 3]
        if getattr(req, "dress_code", None):
            needles.append(req.dress_code.strip().lower())
        if not picked_items:
            return "unsuitable"
        hits = sum(1 for it in picked_items if self._item_matches_occasion(it, needles))
        if hits == len(picked_items):
            return "suitable"
        return "partial" if hits else "unsuitable"

    def _reconcile(
        self, *, req: OutfitRecommendationRequest, picked: List[RecommendedItem], picked_items: List[Any],
        dropped: List[Any], summary: str, styling_notes: List[str], assumptions: List[str],
        limitations: List[str], is_complete: bool,
    ) -> Tuple[str, List[str], List[str], List[str], str]:
        """Server-controlled post-processing so the text matches the outfit.
        Returns (summary, styling_notes, assumptions, limitations, fit_status)."""
        t = _FALLBACK_TEXT["ar" if req.language == "ar" else "en"]
        occ = _occasion_label(req.occasion, req.language)
        act = _occasion_label(req.activity, req.language) if getattr(req, "activity", None) else None
        fit = self._fit_status(picked_items, req)
        if dropped:
            # D10: anything the model wrote may describe removed garments; rewrite deterministically.
            names = "، ".join(p.title for p in picked) if req.language == "ar" else ", ".join(p.title for p in picked)
            summary = t["filtered_summary"].format(
                items=names, state=t["complete_word"] if is_complete else t["incomplete_word"]
            )
            styling_notes = [n for n in styling_notes if not self._mentions_any(n, dropped, kept=picked_items)]
            assumptions = [a for a in assumptions if not self._mentions_any(a, dropped, kept=picked_items)]
            for p in picked:
                if self._mentions_any(p.reason, dropped, kept=picked_items):
                    p.reason = t["generic_reason"].format(occasion=occ)
            # Positions the wardrobe *could* fill but the colour filter emptied.
            present = {p.role for p in picked}
            needed = ["footwear"] if "dress" in present else list(CORE_ROLES)
            for role in needed:
                if role not in present and any(
                    CATEGORY_TO_ROLE.get(taxonomy.normalize_category(d.category), "accessory") == role for d in dropped
                ):
                    cat = ROLE_TO_CATEGORY[role]
                    note = t["unfilled"].format(category=_CATEGORY_AR.get(cat, cat) if req.language == "ar" else cat.lower())
                    if note not in limitations:
                        limitations.append(note)
        if fit == "unsuitable":
            # D11: do not let an unsuitable outfit read as suitable, and strip
            # performance claims the metadata cannot support.
            summary = t["unsuitable_summary"].format(occasion=act or occ)
            note = t["no_occasion_match"].format(occasion=occ)
            if note not in limitations:
                limitations.insert(0, note)
            styling_notes = [n for n in styling_notes if not self._UNSUPPORTED_CLAIM_RE.search(n)]
            assumptions = [a for a in assumptions if not self._UNSUPPORTED_CLAIM_RE.search(a)]
            for p in picked:
                if self._UNSUPPORTED_CLAIM_RE.search(p.reason or ""):
                    p.reason = t["neutral_reason"].format(category=p.category, occasion=occ)
        elif fit == "partial":
            summary = f"{summary} {t['partial_summary'].format(occasion=occ)}".strip()
        return summary, styling_notes, assumptions, limitations, fit

    # ── deterministic fallback (labelled) ────────────────────────────
    def _deterministic(
        self, items: List[Any], req: OutfitRecommendationRequest, context: Dict[str, Any], *, fallback_reason: str
    ) -> OutfitRecommendation:
        occasion_norm = req.occasion.strip().lower()
        season = (req.season or "").lower()
        prefer_colors = {taxonomy.normalize_color(c) for c in req.color_preferences}
        previous = set(req.previous_item_ids)
        banned = self.banned_color_families(req)
        colour_dropped = 0
        if banned:
            kept = [it for it in items if taxonomy.normalize_color(it.color_name) not in banned]
            colour_dropped = len(items) - len(kept)
            items = kept

        def score(it: Any) -> float:
            return self._rule_score(it, req)

        by_role: Dict[str, List[Any]] = {}
        for it in items:
            by_role.setdefault(CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category), "accessory"), []).append(it)

        picked: List[RecommendedItem] = []
        roles_plan: List[str]
        if by_role.get("dress") and not (by_role.get("top") and by_role.get("bottom")):
            roles_plan = ["dress", "footwear"]
        else:
            roles_plan = ["top", "bottom", "footwear"]
        # Evening alone is not a reason for a coat in summer (eval S04: a down
        # parka was proposed for a 31 °C rooftop dinner).
        if season in ("autumn", "winter") or (req.time_of_day in ("evening", "night") and season != "summer"):
            roles_plan.append("outerwear")
        for role in roles_plan:
            cands = by_role.get(role) or []
            if not cands:
                continue
            best = max(cands, key=score)
            reason = self._rule_reason(best, role, req)
            picked.append(RecommendedItem(
                wardrobe_item_id=best.id, role=role, category=taxonomy.normalize_category(best.category),
                title=best.title, subcategory=best.subcategory, color_name=best.color_name,
                color_hex=best.color_hex or "#000000", image_url=storage_public_url(best.image_url),
                reason=reason, analysis_source=getattr(best, "analysis_source", None),
                ai_confidence=getattr(best, "ai_confidence", None),
            ))
        present_roles = {p.role for p in picked}
        missing = self._missing_categories(items, present_roles)
        ar = req.language == "ar"
        t = _FALLBACK_TEXT["ar" if ar else "en"]
        limitations = [t["fallback_notice"]] + [
            (t["missing"].format(category=_CATEGORY_AR.get(m, m)) if ar else t["missing"].format(category=m.lower()))
            for m in missing
        ]
        # Nothing tagged for the occasion at all (eval S16: a suit was proposed
        # for the gym without a word of warning).
        by_id_all = {i.id: i for i in items}
        occ_hits = sum(
            1 for p in picked
            if any(occasion_norm in str(o).lower() or str(o).lower() in occasion_norm
                   for o in _loads(by_id_all[p.wardrobe_item_id].occasions))
        )
        fit = self._fit_status([by_id_all[p.wardrobe_item_id] for p in picked], req)
        if picked and occ_hits == 0:
            limitations.append(t["no_occasion_match"].format(occasion=_occasion_label(req.occasion, req.language)))
        if colour_dropped:
            limitations.append(self._color_limitation(colour_dropped, banned, req.language))
        limitations.extend(self._unrecognised_limitation(req))
        return OutfitRecommendation(
            outfit_id=f"det_{uuid.uuid4().hex[:12]}",
            occasion=req.occasion,
            title=t["title"].format(occasion=_occasion_label(req.occasion, req.language)),
            summary=(t["unsuitable_summary"].format(
                occasion=_occasion_label(req.activity, req.language) if req.activity else _occasion_label(req.occasion, req.language)
            ) if fit == "unsuitable"
                     else t["summary"]),
            items=picked,
            fit_status=fit,
            styling_notes=[],
            limitations=limitations,
            missing_categories=missing,
            assumptions=[],
            is_complete=self._is_complete(present_roles),
            source="deterministic_fallback",
            ai_generated=False,
            model_id=None,
            prompt_version=None,
            fallback_reason=fallback_reason,
            context=context,
        )

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _closet_record(it: Any) -> Dict[str, Any]:
        """Model-facing view of an item: ids + descriptors, no URLs/paths/user data."""
        rec = {
            "wardrobe_item_id": it.id,
            "category": taxonomy.normalize_category(it.category),
            "item_type": it.subcategory or it.title,
            "title": it.title,
            "color": it.color_name,
            "secondary_colors": _loads(getattr(it, "secondary_colors", None)),
            "pattern": it.pattern,
            "style_tags": _loads(it.ai_tags)[:6],
            "occasions": _loads(it.occasions),
            "seasonality": getattr(it, "seasonality", "All-Season"),
            "favorite": bool(it.is_favorite),
        }
        desc = getattr(it, "analysis_description", None)
        if desc:
            rec["description"] = desc[:200]
        conf = getattr(it, "ai_confidence", None)
        if conf is not None:
            rec["metadata_confidence"] = round(float(conf), 2)
        return rec

    @staticmethod
    def _context(req: OutfitRecommendationRequest) -> Dict[str, Any]:
        ctx = {k: v for k, v in req.model_dump().items() if v not in (None, [], "")}
        ctx["occasion"] = req.occasion
        return ctx

    @staticmethod
    def _missing_categories(items: List[Any], present_roles: set) -> List[str]:
        """Core positions (top/bottom/footwear, or dress+footwear) the wardrobe
        cannot fill at all — reported, never fabricated (Scenario D)."""
        available = {CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category), "accessory") for it in items}
        missing: List[str] = []
        if "dress" in present_roles:
            needed = ["footwear"]
        else:
            needed = list(CORE_ROLES)
        for role in needed:
            if role not in present_roles and role not in available:
                missing.append(ROLE_TO_CATEGORY[role])
        return missing

    @staticmethod
    def _is_complete(present_roles: set) -> bool:
        return ("dress" in present_roles or {"top", "bottom"} <= present_roles) and "footwear" in present_roles

    @staticmethod
    def _rule_score(it: Any, req: OutfitRecommendationRequest) -> float:
        """Constraint-aware wardrobe scorer shared by the deterministic fallback and
        the D12 core-position completion. Banned colours / excluded ids are filtered
        by the callers; this only ranks eligible items."""
        occasion_norm = req.occasion.strip().lower()
        season = (req.season or "").lower()
        prefer_colors = {taxonomy.normalize_color(c) for c in req.color_preferences}
        s = 0.0
        occ = [str(o).lower() for o in _loads(it.occasions)]
        if any(occasion_norm in o or o in occasion_norm for o in occ):
            s += 50
        seas = (getattr(it, "seasonality", "") or "").lower()
        if season and (seas == season or seas == "all-season"):
            s += 12
        elif season and seas and seas != "all-season":
            s -= 15
        if it.is_favorite or it.wear_frequency == "favorite":
            s += 15
        if taxonomy.normalize_color(it.color_name) in prefer_colors:
            s += 10
        if taxonomy.normalize_color(it.color_name) in ("Black", "White", "Navy", "Beige", "Grey", "Ivory"):
            s += 5
        if it.id in set(req.previous_item_ids):
            s -= 25  # "another outfit": vary when possible
        return s

    def _complete_core_positions(
        self, picked: List[RecommendedItem], items: List[Any], req: OutfitRecommendationRequest
    ) -> List[RecommendedItem]:
        """D12: fill core positions the model left empty (after an id mix-up, a
        duplicate, or a colour-filtered piece) with the best *eligible* wardrobe
        item. Eligible = right category, not excluded by id, not in a banned colour,
        not already used. Each added piece is labelled selected_by="rule_matcher"
        and carries a rule reason — never attributed to the model."""
        present = {p.role for p in picked}
        if "dress" in present:
            needed = ["footwear"]
        elif not ({"top", "bottom"} & present) and any(
            CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category)) == "dress" for it in items
        ) and not any(CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category)) in ("top", "bottom") for it in items):
            needed = ["dress", "footwear"]
        else:
            needed = list(CORE_ROLES)
        banned = self.banned_color_families(req)
        used = {p.wardrobe_item_id for p in picked}
        added: List[RecommendedItem] = []
        for role in needed:
            if role in present:
                continue
            cands = [
                it for it in items
                if CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category), "accessory") == role
                and it.id not in used and it.id not in req.excluded_item_ids
                and not (banned and taxonomy.normalize_color(it.color_name) in banned)
            ]
            if not cands:
                continue
            best = max(cands, key=lambda it: self._rule_score(it, req))
            added.append(RecommendedItem(
                wardrobe_item_id=best.id, role=role, category=taxonomy.normalize_category(best.category),
                title=best.title, subcategory=best.subcategory, color_name=best.color_name,
                color_hex=best.color_hex or "#000000", image_url=storage_public_url(best.image_url),
                reason=self._rule_reason(best, role, req), analysis_source=getattr(best, "analysis_source", None),
                ai_confidence=getattr(best, "ai_confidence", None), selected_by="rule_matcher",
            ))
            used.add(best.id)
            present.add(role)
            logger.info("wardrobe_stylist_core_position_completed", item_id=best.id, role=role)
        return added

    @staticmethod
    def _rule_reason(it: Any, role: str, req: OutfitRecommendationRequest) -> str:
        t = _FALLBACK_TEXT["ar" if req.language == "ar" else "en"]
        bits = []
        occ = [str(o) for o in _loads(it.occasions)]
        if any(req.occasion.lower() in o.lower() or o.lower() in req.occasion.lower() for o in occ):
            bits.append(t["r_tagged"].format(occasion=_occasion_label(req.occasion, "ar") if req.language == "ar" else req.occasion.lower()))
        if req.season and (getattr(it, "seasonality", "") or "").lower() in (req.season, "all-season"):
            bits.append(t["r_season"].format(season=_SEASON_AR.get(req.season, req.season) if req.language == "ar" else req.season))
        if it.is_favorite:
            bits.append(t["r_favourite"])
        color = taxonomy.normalize_color(it.color_name)
        if color in ("Black", "White", "Navy", "Beige", "Grey", "Ivory"):
            bits.append(t["r_neutral"].format(color=_COLOR_AR.get(color, color) if req.language == "ar" else color.lower()))
        sep = "، " if req.language == "ar" else ", "
        return (f"{it.title}: " + sep.join(bits)) if bits else t["r_best_available"].format(title=it.title, role=_ROLE_AR.get(role, role) if req.language == "ar" else role)

    @staticmethod
    def _str(v: Any, limit: int) -> Optional[str]:
        if isinstance(v, str) and v.strip():
            return " ".join(v.split())[:limit]
        return None

    @classmethod
    def _str_list(cls, v: Any, max_items: int, limit: int) -> List[str]:
        if not isinstance(v, list):
            return []
        out: List[str] = []
        for x in v:
            s = cls._str(x, limit)
            if s and s not in out:
                out.append(s)
            if len(out) >= max_items:
                break
        return out
