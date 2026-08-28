import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.repositories.stylist_repository import StylistRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.providers.orchestrator import MultiProviderAIOrchestrator
from backend.app.services.styling_engine import StylingEngine


class StylistService:
    def __init__(self, db: Session):
        self.db = db
        self.stylist_repo = StylistRepository(db)
        self.catalog_repo = CatalogRepository(db)
        self.profile_repo = ProfileRepository(db)
        self.wardrobe_repo = WardrobeRepository(db)
        self.orchestrator = MultiProviderAIOrchestrator()

    async def interact_with_stylist(
        self,
        user_id: Optional[int],
        prompt: str,
        session_id: Optional[int] = None,
        occasion: Optional[str] = None,
        budget_limit: Optional[float] = None,
        voice_input_used: bool = False
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
        user_styles = json.loads(usp.style_archetypes) if usp and usp.style_archetypes else ["Smart Casual", "Quiet Luxury"]
        user_colors = json.loads(usp.preferred_colors) if usp and usp.preferred_colors else ["Navy", "Beige", "Black"]
        max_budget = budget_limit or (usp.budget_per_outfit_max if usp else 450.0)

        # 4. Parse user intent, occasion, style, and slot expectations
        intent = StylingEngine.parse_intent(
            prompt=prompt,
            occasion_hint=occasion,
            budget_hint=max_budget,
            user_styles=user_styles,
            user_colors=user_colors
        )

        # 5. Retrieve candidate products from real database catalog
        all_products = self.catalog_repo.filter_products(limit=100)

        # 6. Compose strict slot-based complete outfits grounded in the catalog
        recommended_outfits = StylingEngine.compose_outfits(
            available_products=all_products,
            intent=intent,
            user_profile=usp,
            max_outfits=2
        )

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
            "recommendations": recommended_outfits,
            "created_at": assistant_msg.created_at
        }
