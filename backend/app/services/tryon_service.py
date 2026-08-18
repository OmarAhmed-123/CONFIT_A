import json
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from backend.app.repositories.tryon_repository import TryOnRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.providers.tryon_provider import VirtualTryOnProvider
from backend.app.services.styling.ontology import SlotType, classify_product_slot
from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine, SlotResolutionResult
from backend.app.core.exceptions import ResourceNotFoundError


class TryOnService:
    def __init__(self, db: Session):
        self.db = db
        self.tryon_repo = TryOnRepository(db)
        self.catalog_repo = CatalogRepository(db)
        self.profile_repo = ProfileRepository(db)
        self.vton_provider = VirtualTryOnProvider()
        self.slot_engine = SlotLayeringEngine()

    def resolve_product_slot_and_layer(self, product: Any) -> Tuple[str, int]:
        slot, layer, _ = self.slot_engine.map_category_to_slot(product)
        return slot, layer

    async def execute_multi_garment_tryon(
        self,
        product_ids: Optional[List[int]] = None,
        slot_mapping: Optional[Dict[str, int]] = None,
        user_image_url: Optional[str] = None,
        user_image_base64: Optional[str] = None,
        avatar_model_id: Optional[str] = "avatar_athletic_m",
        gender_mode: Optional[str] = "infer_from_image",
        user_id: Optional[int] = None,
        existing_session_id: Optional[int] = None,
        consent_retain_photo: bool = False
    ) -> Dict[str, Any]:
        target_ids = list(product_ids or [])
        if slot_mapping:
            for pid in slot_mapping.values():
                if pid and pid not in target_ids:
                    target_ids.append(pid)

        if not target_ids:
            featured = self.catalog_repo.filter_products(is_featured=True, limit=1)
            target_ids = [featured[0].id] if featured else [1]

        products = [self.catalog_repo.get_product_by_id(pid) for pid in target_ids]
        products = [p for p in products if p is not None]

        if not products:
            raise ResourceNotFoundError("Products", str(target_ids))

        scaling = 1.0
        if user_id:
            usp = self.profile_repo.get_by_user_id(user_id)
            if usp:
                body = self.profile_repo.get_decrypted_body_data(usp)
                if body.get("height_cm"):
                    scaling = round(float(body["height_cm"]) / 175.0, 2)

        # Run SlotLayeringEngine to incrementally resolve each product with conflict handling
        accumulated_items = []
        for p in products:
            res = self.slot_engine.resolve_and_apply(accumulated_items, p)
            accumulated_items = res.final_applied_items

        applied_items = accumulated_items
        computed_slot_map = {(it.get("slot_type") or it.get("position")): it["product_id"] for it in applied_items}
        recommended_sizes = {it["position"]: it.get("selected_size", "M") for it in applied_items}

        effective_input_image = user_image_url or (f"https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600&auto=format&fit=crop&q=80" if "female" in (avatar_model_id or "") else f"https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600&auto=format&fit=crop&q=80")

        vton_result = await self.vton_provider.render_multi_garment_tryon(
            user_image_url=effective_input_image,
            applied_items=applied_items,
            gender_mode=gender_mode or "infer_from_image",
            body_scaling=scaling
        )

        total_price = sum(it["price"] for it in applied_items)
        first_product_id = applied_items[0]["product_id"] if applied_items else products[0].id

        if existing_session_id:
            session = self.tryon_repo.get_tryon_session(existing_session_id)
            if session:
                session.product_id = first_product_id
                session.input_user_image_url = effective_input_image
                session.garment_image_url = applied_items[0]["image_url"] if applied_items else products[0].thumbnail_url
                session.rendered_result_url = vton_result.get("rendered_image_url", effective_input_image)
                session.applied_items_json = json.dumps(applied_items)
                session.slot_mapping_json = json.dumps(computed_slot_map)
                session.layering_order_json = json.dumps([it["position"] for it in applied_items])
                session.fit_confidence_score = vton_result.get("fit_confidence", 96)
                session.body_fit_verdict = vton_result.get("fit_verdict", "True to Size (Optimal Drape)")
                self.db.commit()
                self.db.refresh(session)
            else:
                session = self.tryon_repo.create_tryon_session(
                    product_id=first_product_id,
                    input_user_image_url=effective_input_image,
                    garment_image_url=applied_items[0]["image_url"] if applied_items else products[0].thumbnail_url,
                    rendered_result_url=vton_result.get("rendered_image_url", effective_input_image),
                    applied_items=applied_items,
                    slot_mapping=computed_slot_map,
                    user_id=user_id,
                    fit_verdict=vton_result.get("fit_verdict", "True to Size (Optimal Drape)"),
                    fit_confidence_score=vton_result.get("fit_confidence", 96),
                    body_scaling_factor=scaling,
                    consent_retained=consent_retain_photo,
                    expiry_hours=24 if not consent_retain_photo else 720
                )
        else:
            session = self.tryon_repo.create_tryon_session(
                product_id=first_product_id,
                input_user_image_url=effective_input_image,
                garment_image_url=applied_items[0]["image_url"] if applied_items else products[0].thumbnail_url,
                rendered_result_url=vton_result.get("rendered_image_url", effective_input_image),
                applied_items=applied_items,
                slot_mapping=computed_slot_map,
                user_id=user_id,
                fit_verdict=vton_result.get("fit_verdict", "True to Size (Optimal Drape)"),
                fit_confidence_score=vton_result.get("fit_confidence", 96),
                body_scaling_factor=scaling,
                consent_retained=consent_retain_photo,
                expiry_hours=24 if not consent_retain_photo else 720
            )

        return {
            "session_id": session.id,
            "status": "completed",
            "user_reference_image": effective_input_image,
            "rendered_result_url": session.rendered_result_url,
            "before_after_split_url": session.rendered_result_url,
            "applied_items": applied_items,
            "total_price": round(total_price, 2),
            "fit_confidence_score": session.fit_confidence_score,
            "body_fit_verdict": session.body_fit_verdict,
            "recommended_sizes": recommended_sizes,
            "ai_disclosure": vton_result.get("ai_disclosure"),
            "traceability_hash": vton_result.get("traceability_hash"),
            "layering_order": [it["position"] for it in applied_items],
            "dynamic_prompt_generated": vton_result.get("dynamic_prompt_generated"),
            "expires_at": session.expires_at
        }

    async def apply_item_to_session(
        self,
        session_id: int,
        product_id: int,
        slot: Optional[str] = None,
        replace_if_occupied: bool = True,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        sess = self.tryon_repo.get_tryon_session(session_id)
        current_items = []
        user_img = None

        if sess:
            user_img = sess.input_user_image_url
            try:
                current_items = json.loads(sess.applied_items_json) if sess.applied_items_json else []
            except Exception:
                current_items = []

        target_prod = self.catalog_repo.get_product_by_id(product_id)
        if not target_prod:
            raise ResourceNotFoundError("Product", product_id)

        # Run SlotLayeringEngine for slot resolution & conflict replacement
        res: SlotResolutionResult = self.slot_engine.resolve_and_apply(
            existing_items=current_items,
            new_product=target_prod,
            target_slot_override=slot
        )

        updated_pids = [it["product_id"] for it in res.final_applied_items]

        return await self.execute_multi_garment_tryon(
            product_ids=updated_pids,
            user_image_url=user_img,
            existing_session_id=session_id,
            user_id=user_id
        )

    async def remove_item_from_session(
        self,
        session_id: int,
        product_id: Optional[int] = None,
        slot: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        sess = self.tryon_repo.get_tryon_session(session_id)
        current_items = []
        user_img = None

        if sess:
            user_img = sess.input_user_image_url
            try:
                current_items = json.loads(sess.applied_items_json) if sess.applied_items_json else []
            except Exception:
                current_items = []

        # Run SlotLayeringEngine to remove target item/slot
        res: SlotResolutionResult = self.slot_engine.resolve_and_remove(
            existing_items=current_items,
            product_id=product_id,
            slot=slot
        )

        updated_pids = [it["product_id"] for it in res.final_applied_items]

        return await self.execute_multi_garment_tryon(
            product_ids=updated_pids,
            user_image_url=user_img,
            existing_session_id=session_id,
            user_id=user_id
        )

    async def reorder_session_items(
        self,
        session_id: int,
        slot_order: List[str],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        sess = self.tryon_repo.get_tryon_session(session_id)
        if not sess:
            raise ResourceNotFoundError("TryOnSession", session_id)

        try:
            existing_items = json.loads(sess.applied_items_json)
            p_ids = [it["product_id"] for it in existing_items]
        except Exception:
            p_ids = [sess.product_id] if sess.product_id else [1]

        return await self.execute_multi_garment_tryon(
            product_ids=p_ids,
            user_image_url=sess.input_user_image_url,
            existing_session_id=session_id,
            user_id=user_id
        )

    async def execute_animated_tryon(
        self,
        product_ids: Optional[List[int]] = None,
        slot_mapping: Optional[Dict[str, int]] = None,
        user_image_url: Optional[str] = None,
        avatar_model_id: Optional[str] = "avatar_athletic_m",
        gender_mode: Optional[str] = "infer_from_image",
        output_aspect: Optional[str] = "9:16",
        background_mode: Optional[str] = "studio",
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        multi_data = await self.execute_multi_garment_tryon(
            product_ids=product_ids,
            slot_mapping=slot_mapping,
            user_image_url=user_image_url,
            avatar_model_id=avatar_model_id,
            gender_mode=gender_mode,
            user_id=user_id
        )

        effective_image = user_image_url or (f"https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600" if "female" in (avatar_model_id or "") else f"https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600")

        anim_res = await self.vton_provider.render_animated_tryon(
            user_image_url=effective_image,
            applied_items=multi_data["applied_items"],
            gender_mode=gender_mode or "infer_from_image",
            output_aspect=output_aspect or "9:16",
            background_mode=background_mode or "studio"
        )

        return {
            "session_id": multi_data["session_id"],
            "status": "completed",
            "animation_style": anim_res["animation_style"],
            "output_aspect": anim_res["output_aspect"],
            "rendered_animation_url": multi_data["rendered_result_url"],
            "keyframes_sequence": anim_res["keyframes_sequence"],
            "fit_confidence_score": anim_res["fit_confidence_score"],
            "body_fit_verdict": anim_res["body_fit_verdict"],
            "traceability_hash": anim_res["traceability_hash"],
            "ai_disclosure": anim_res["ai_disclosure"],
            "dynamic_animation_prompt": anim_res["dynamic_animation_prompt"],
            "applied_items": multi_data["applied_items"],
            "total_price": multi_data["total_price"]
        }

    async def execute_tryon(
        self,
        product_id: int,
        user_image_url: Optional[str] = None,
        user_image_base64: Optional[str] = None,
        avatar_model_id: Optional[str] = "avatar_athletic_m",
        user_id: Optional[int] = None,
        consent_retain_photo: bool = False
    ) -> Dict[str, Any]:
        product = self.catalog_repo.get_product_by_id(product_id)
        if not product:
            raise ResourceNotFoundError("Product", product_id)

        res = await self.execute_multi_garment_tryon(
            product_ids=[product_id],
            user_image_url=user_image_url,
            user_image_base64=user_image_base64,
            avatar_model_id=avatar_model_id,
            user_id=user_id,
            consent_retain_photo=consent_retain_photo
        )

        return {
            "session_id": res["session_id"],
            "product_id": product.id,
            "product_title": product.title,
            "brand_name": product.brand.brand_name if product.brand else "CONFIT",
            "status": "completed",
            "original_item_image": product.thumbnail_url,
            "rendered_result_url": res["rendered_result_url"],
            "fit_confidence_score": res["fit_confidence_score"],
            "body_fit_verdict": res["body_fit_verdict"],
            "recommended_size": product.skus[0].size if product.skus else "M",
            "ai_disclosure": res["ai_disclosure"],
            "traceability_hash": res["traceability_hash"],
            "expires_at": res["expires_at"]
        }

    def validate_image(self, image_url_or_base64: str) -> Dict[str, Any]:
        return self.vton_provider.validate_uploaded_image(image_url_or_base64)
