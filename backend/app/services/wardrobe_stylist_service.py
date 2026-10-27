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

        picked, rejected, limitations = self._validate_selection(raw, items, req)
        if not picked:
            raise ProviderIntegrationError(
                "watsonx", "model did not reference any valid wardrobe item", retryable=True
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

        return OutfitRecommendation(
            outfit_id=f"wx_{uuid.uuid4().hex[:12]}",
            occasion=req.occasion,
            title=self._str(raw.get("title"), 80) or f"{req.occasion} look",
            summary=self._str(raw.get("summary"), 600) or "A coordinated outfit from your wardrobe.",
            items=picked,
            styling_notes=self._str_list(raw.get("styling_notes"), 4, 240),
            limitations=limitations[:6],
            missing_categories=missing,
            assumptions=self._str_list(raw.get("assumptions"), 4, 200),
            is_complete=self._is_complete(present_roles),
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
                logger.info("wardrobe_stylist_banned_colour_dropped", item_id=item_id)
                continue
            real_role = CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category), "accessory")
            claimed = str(entry.get("role") or "").strip().lower()
            if claimed != real_role:
                # Trust the stored (user-correctable) category, not the model.
                logger.info("wardrobe_stylist_role_corrected", item_id=item_id, claimed=claimed, real=real_role)
            if real_role in seen_roles and real_role != "accessory":
                continue  # one piece per position
            if real_role == "dress" and {"top", "bottom"} & seen_roles:
                continue
            if real_role in ("top", "bottom") and "dress" in seen_roles:
                continue
            reason = self._str(entry.get("reason"), 400) or f"Selected for a {req.occasion.lower()} setting."
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
        limitations.extend(self._unrecognised_limitation(req))
        for lim in self._str_list(raw.get("limitations"), 4, 240):
            if lim not in limitations:
                limitations.append(lim)
        return picked, rejected, limitations

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
            if it.id in previous:
                s -= 25  # "another outfit": vary when possible
            return s

        by_role: Dict[str, List[Any]] = {}
        for it in items:
            by_role.setdefault(CATEGORY_TO_ROLE.get(taxonomy.normalize_category(it.category), "accessory"), []).append(it)

        picked: List[RecommendedItem] = []
        roles_plan: List[str]
        if by_role.get("dress") and not (by_role.get("top") and by_role.get("bottom")):
            roles_plan = ["dress", "footwear"]
        else:
            roles_plan = ["top", "bottom", "footwear"]
        if season in ("autumn", "winter") or (req.time_of_day in ("evening", "night")):
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
        limitations = [
            "This outfit was assembled by CONFIT's rule-based matcher, not by the AI stylist "
            "(the language model was unavailable). Reasons are generic.",
        ] + [f"No {m.lower()} in your wardrobe to complete this look." for m in missing]
        if colour_dropped:
            limitations.append(self._color_limitation(colour_dropped, banned, req.language))
        limitations.extend(self._unrecognised_limitation(req))
        return OutfitRecommendation(
            outfit_id=f"det_{uuid.uuid4().hex[:12]}",
            occasion=req.occasion,
            title=f"{req.occasion} from your wardrobe",
            summary=(
                "Pieces chosen by occasion tags, season, favourites and neutral colours. "
                "Configure watsonx.ai for a reasoned, context-specific recommendation."
            ),
            items=picked,
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
    def _rule_reason(it: Any, role: str, req: OutfitRecommendationRequest) -> str:
        bits = []
        occ = [str(o) for o in _loads(it.occasions)]
        if any(req.occasion.lower() in o.lower() or o.lower() in req.occasion.lower() for o in occ):
            bits.append(f"tagged for {req.occasion.lower()}")
        if req.season and (getattr(it, "seasonality", "") or "").lower() in (req.season, "all-season"):
            bits.append(f"suits {req.season}")
        if it.is_favorite:
            bits.append("one of your favourites")
        color = taxonomy.normalize_color(it.color_name)
        if color in ("Black", "White", "Navy", "Beige", "Grey", "Ivory"):
            bits.append(f"{color.lower()} pairs easily")
        return (f"{it.title}: " + ", ".join(bits)) if bits else f"{it.title}: best available {role} for this request."

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
