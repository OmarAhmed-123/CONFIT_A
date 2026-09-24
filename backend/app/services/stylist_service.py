import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.repositories.stylist_repository import StylistRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.providers.orchestrator import get_orchestrator
from backend.app.services.styling_engine import StylingEngine
from backend.app.services.recommendation_constraints import constraints_from_payload, apply_constraints


class StylistService:
    def __init__(self, db: Session):
        self.db = db
        self.stylist_repo = StylistRepository(db)
        self.catalog_repo = CatalogRepository(db)
        self.profile_repo = ProfileRepository(db)
        self.wardrobe_repo = WardrobeRepository(db)
        # Shared process-wide orchestrator so provider quarantine (cooldown)
        # state actually persists across requests.
        self.orchestrator = get_orchestrator()

    async def interact_with_stylist(
        self,
        user_id: Optional[int],
        prompt: str,
        session_id: Optional[int] = None,
        occasion: Optional[str] = None,
        budget_limit: Optional[float] = None,
        voice_input_used: bool = False,
        recommendation_constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # 1. Retrieve or create session (supports guest user_id=None)
        session = self.stylist_repo.get_or_create_session(user_id, session_id)

        # 2. Add user message
        user_msg = self.stylist_repo.add_message(
            session_id=session.id,
            sender="user",
            content=prompt
        )

        # 3. Retrieve user profile if authenticated
        usp = self.profile_repo.get_by_user_id(user_id) if user_id else None
        # Whether a PERSISTED profile actually provided the styles. The fallback
        # list below is a matching input, not a fact about the shopper — the
        # prose used to say "tailored to your Smart Casual profile" to an
        # anonymous caller because that distinction did not exist (measured
        # 2026-09-24; see services/styling/attribution.py).
        profile_styles_present = bool(usp and usp.style_archetypes)
        user_styles = json.loads(usp.style_archetypes) if profile_styles_present else ["Smart Casual", "Quiet Luxury"]
        user_colors = json.loads(usp.preferred_colors) if usp and usp.preferred_colors else ["Navy", "Beige", "Black"]
        # Only a user-stated budget (explicit request param, or text the parser
        # extracts) is a HARD constraint. A stored profile default is a soft
        # preference, so it must NOT mark the budget as explicit.
        explicit_budget = budget_limit if budget_limit is not None else None
        max_budget = budget_limit or (usp.budget_per_outfit_max if usp else 450.0)

        # 4. Parse user intent, occasion, style, and slot expectations
        intent = StylingEngine.parse_intent(
            prompt=prompt,
            occasion_hint=occasion,
            budget_hint=explicit_budget,
            user_styles=user_styles,
            user_colors=user_colors,
            profile_styles_present=profile_styles_present,
        )
        # Ensure the composer always has a numeric ceiling for scoring even when
        # no explicit budget was stated (soft profile default).
        intent.setdefault("detected_budget", max_budget)
        if not intent.get("detected_budget"):
            intent["detected_budget"] = max_budget

        # 5. Graceful handling of ambiguous / low-signal requests (BRD 21,
        #    E2E-12): ask a clarifying question instead of returning confident
        #    fabricated outfits for gibberish or empty input.
        if intent.get("is_ambiguous"):
            clarify_text = (
                "I want to style you well, but I didn't catch a specific occasion, "
                "style, or budget in that. Could you tell me a bit more — for example "
                "'a smart casual work outfit under $500' or 'a formal wedding look'? "
                "You can also tap an occasion: Work, Wedding, Party, or Casual."
            )
            assistant_msg = self.stylist_repo.add_message(
                session_id=session.id,
                sender="assistant",
                content=clarify_text,
                intent_json=intent,
                recommendations_json=[]
            )
            # No provider was called on this path (the prompt was too vague to
            # act on), so there is no engine to attribute. `engine: "none"` is
            # stated rather than left absent, so a client cannot mistake a
            # clarifying question for a generated styling answer.
            return {
                "id": assistant_msg.id,
                "session_id": session.id,
                "sender": "assistant",
                "content": assistant_msg.content,
                "audio_url": None,
                "intent_detected": intent,
                "engine": "none",
                "recommendations": [],
                "created_at": assistant_msg.created_at
            }

        # 6. Retrieve candidate products from the real catalog. Availability
        #    gate (BRD 15): only products with at least one in-stock SKU are
        #    eligible for recommendation; out-of-stock items are never composed.
        all_products = [
            p for p in self.catalog_repo.filter_products(limit=100)
            if getattr(p, "skus", None) and any(s.is_in_stock and s.stock_level > 0 for s in p.skus)
        ]

        # 6b. Structured recommendation constraints. Palette is authoritative
        #     when it maps to catalog colour fields; fit is authoritative only
        #     where a concrete size from the request/profile can be checked
        #     against SKU stock. No AI and no fake confidence scores.
        constraint_meta = None
        if recommendation_constraints or usp:
            constraints = constraints_from_payload(recommendation_constraints, usp)
            all_products, constraint_meta = apply_constraints(all_products, constraints)
            intent["recommendation_constraints"] = constraint_meta

        # 7. Compose strict slot-based complete outfits grounded in the catalog
        recommended_outfits, alternatives_meta = StylingEngine.compose_outfits_with_meta(
            available_products=all_products,
            intent=intent,
            user_profile=usp,
            max_outfits=2
        )
        # Whether a second look was requested, published, or suppressed because it
        # held the same products as the first — part of the record, not a log
        # detail (styling/diversity.py explains the rule).
        if alternatives_meta.get("suppressed"):
            intent["alternatives"] = alternatives_meta

        primary_outfit = recommended_outfits[0] if recommended_outfits else None

        # 7. Generate Natural Language Explanation GROUNDED ON THE SELECTED OUTFIT
        ai_result = await self.orchestrator.generate_styling_advice(
            prompt=prompt,
            user_style_tags=user_styles,
            preferred_colors=user_colors,
            budget_limit=max_budget,
            selected_outfit=primary_outfit,
            intent=intent
        )

        # 8. Save assistant response
        #
        # WHICH ENGINE ANSWERED IS PART OF THE RECORD, NOT A LOG DETAIL.
        # The orchestrator already labels the answer truthfully — a real call
        # returns "<Provider> <model the provider actually served>", and a total
        # provider failure returns "CONFIT Grounded Styling Engine". That label
        # used to be computed and then DROPPED here: not persisted, not returned,
        # so neither the consumer nor a reviewer could tell a provider answer
        # from deterministic fallback prose while the capability flag still said
        # the stylist was live. It is now written into the stored message and
        # returned to the caller.
        engine = ai_result.get("provider_used")
        intent["engine"] = engine
        assistant_msg = self.stylist_repo.add_message(
            session_id=session.id,
            sender="assistant",
            content=ai_result.get("styling_advice_text", "Here is your curated complete look."),
            intent_json=intent,
            recommendations_json=recommended_outfits
        )

        return {
            "id": assistant_msg.id,
            "session_id": session.id,
            "sender": "assistant",
            "content": assistant_msg.content,
            "audio_url": None,
            "intent_detected": intent,
            "engine": engine,
            "recommendations": recommended_outfits,
            "created_at": assistant_msg.created_at
        }
