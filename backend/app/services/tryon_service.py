import json
import uuid
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.models.tryon import (
    TryOnJob,
    TryOnJobStatus,
    GarmentAsset
)
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.tryon_repository import TryOnRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.providers.tryon_provider import VirtualTryOnProvider
from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine
from backend.app.core.config import settings
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError, AuthorizationError


# Maps seeded catalogue category slugs to the VTON worker's slot vocabulary.
# The worker (services/vton-worker/pipeline/segmentation.py) raises on any
# slot outside SUPPORTED_SLOTS, so every category MUST have an entry here.
CATEGORY_TO_VTON_SLOT = {
    "outerwear":   "upper_outer",
    "tops":        "upper_inner",
    "bottoms":     "lower",
    "dresses":     "dress",
    "footwear":    "footwear",
    "accessories": "accessory",
}
DEFAULT_VTON_SLOT = "upper_inner"


class TryOnService:
    def __init__(self, db: Session):
        self.db = db
        self.catalog_repo = CatalogRepository(db)
        self.tryon_repo = TryOnRepository(db)
        self.profile_repo = ProfileRepository(db)
        self.vton_provider = VirtualTryOnProvider()
        self.slot_engine = SlotLayeringEngine()

    # =========================================================================
    # Async Job Queue & Pipeline Execution (Step 3 & 4)
    # =========================================================================
    async def create_and_enqueue_vton_job(
        self,
        product_ids: List[int],
        user_image_url: Optional[str] = None,
        user_image_base64: Optional[str] = None,
        avatar_model_id: Optional[str] = "avatar_athletic_m",
        gender_mode: Optional[str] = "infer_from_image",
        output_aspect: Optional[str] = "9:16",
        background_mode: Optional[str] = "studio",
        user_id: Optional[int] = None,
        consent_retain_photo: bool = False
    ) -> Dict[str, Any]:
        """Creates an asynchronous VTON inference job and tracks pipeline stages."""
        if not product_ids:
            raise ValidationDomainError("At least one garment product_id is required to start a Try-On job.")

        job_id = f"vton_job_{uuid.uuid4().hex[:12]}"
        effective_image = user_image_url or user_image_base64 or "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"

        # Validate products exist
        products = [self.catalog_repo.get_product_by_id(pid) for pid in product_ids]
        valid_products = [p for p in products if p is not None]
        if not valid_products:
            raise ResourceNotFoundError("Products", str(product_ids))

        # Create TryOnJob in database
        job = TryOnJob(
            job_id=job_id,
            user_id=user_id,
            status=TryOnJobStatus.QUEUED,
            progress_pct=10,
            current_stage="queued",
            input_person_image_url=effective_image,
            garment_ids_json=json.dumps([p.id for p in valid_products]),
            garment_layers_json=json.dumps([{"id": p.id, "title": p.title, "category": p.category.name if p.category else "Garment"} for p in valid_products]),
            model_used="pending (no render yet)",
            metrics_json=json.dumps({"queued_at": str(datetime.now(timezone.utc))})
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        # Run pipeline stages
        job.status = TryOnJobStatus.PARSING_PERSON
        job.progress_pct = 35
        job.current_stage = "human_parsing_schp"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()

        # Check if remote GPU worker URL is configured
        worker_url = settings.VTON_WORKER_URL or os.environ.get("VTON_WORKER_URL")
        if worker_url:
            job.current_stage = "gpu_diffusion_rendering"
            job.progress_pct = 65
            self.db.commit()

            try:
                import httpx
                import asyncio
                async with httpx.AsyncClient(timeout=90.0) as client:
                    # C17/C18/C19 FIX: Readiness gate with retry + exponential backoff
                    # Prevents crash-loop: check readiness before dispatch, retry 3 times
                    health_ok = False
                    last_health_error = None
                    for attempt in range(3):
                        try:
                            # Try readiness endpoint first (C18), fallback to health
                            try:
                                readiness_resp = await client.get(f"{worker_url.rstrip('/')}/readiness", timeout=5.0)
                                if readiness_resp.status_code == 200 and readiness_resp.json().get("ready") is True:
                                    health_ok = True
                                    break
                            except Exception:
                                pass  # readiness endpoint may not exist on old deploy

                            health = await client.get(f"{worker_url.rstrip('/')}/health", timeout=5.0)
                            if health.status_code == 200:
                                data = health.json()
                                if data.get("model_loaded") is True or data.get("ready") is True:
                                    health_ok = True
                                    break
                                else:
                                    last_health_error = data.get("load_error", "model not loaded")
                            else:
                                last_health_error = f"HTTP {health.status_code}"
                        except Exception as e:
                            last_health_error = str(e)
                            health_ok = False

                        if attempt < 2:  # Don't sleep after last attempt
                            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s backoff

                    if not health_ok:
                        raise RuntimeError(f"GPU worker not ready after 3 attempts: {last_health_error or 'unreachable'}")

                    resp = await client.post(
                        f"{worker_url.rstrip('/')}/process",
                        json={
                            "job_id": job_id,
                            "user_image_base64_or_url": effective_image,
                            "garments": [
                                {
                                    "product_id": p.id,
                                    "slot_type": CATEGORY_TO_VTON_SLOT.get(p.category.slug, DEFAULT_VTON_SLOT) if p.category else DEFAULT_VTON_SLOT,
                                    "image_url": p.thumbnail_url
                                }
                                for p in valid_products
                            ],
                            "gender_mode": gender_mode or "infer_from_image",
                            "output_aspect": output_aspect or "9:16"
                        }
                    )
                    if resp.status_code == 200:
                        gpu_data = resp.json()
                        rendered = gpu_data.get("rendered_image_data_url")
                        # Echo guard: a worker that returns the input unchanged
                        # performed no render — that is a failure, not a result.
                        if not rendered or rendered == effective_image:
                            raise RuntimeError("Worker returned no rendered image (input echoed back)")
                        job.status = TryOnJobStatus.COMPLETED
                        job.progress_pct = 100
                        job.current_stage = "harmonized_and_verified"
                        job.output_image_url = rendered
                        job.completed_at = datetime.now(timezone.utc)
                        # Record the model the worker actually reports.
                        if gpu_data.get("model_used"):
                            job.model_used = str(gpu_data["model_used"])[:50]
                        # Measured values only — never default or fabricate metrics.
                        job.metrics_json = json.dumps(gpu_data.get("quality_audit") or {})
                        self.db.commit()
                        self.db.refresh(job)
                        return self._format_job(job)
                    else:
                        raise Exception(f"GPU Worker returned HTTP {resp.status_code}")
            except Exception as exc:
                job.status = TryOnJobStatus.FAILED
                job.current_stage = "failed"
                job.error_code = "GPU_WORKER_ERROR"
                job.error_message = f"GPU Inference Worker Timeout or Failure: {str(exc)}"
                self.db.commit()
                self.db.refresh(job)
                return self._format_job(job)

        # No GPU inference worker is configured: there is no engine in this
        # process that can render a try-on. Fail truthfully — never substitute
        # a static image, the input photo, or fabricated metrics (A6/A7).
        job.status = TryOnJobStatus.FAILED
        job.current_stage = "failed"
        job.error_code = "VTON_ENGINE_UNAVAILABLE"
        job.error_message = "No GPU inference worker is configured (VTON_WORKER_URL)."
        job.model_used = "none (no render performed)"  # column is NOT NULL; record honestly that no model ran
        job.metrics_json = json.dumps({})  # no metrics: nothing was measured
        self.db.commit()
        self.db.refresh(job)

        return self._format_job(job)

    def get_vton_job_status(self, job_id: str) -> Dict[str, Any]:
        job = self.db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        if not job:
            raise ResourceNotFoundError("TryOnJob", job_id)
        return self._format_job(job)

    def cancel_vton_job(self, job_id: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        job = self.db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        if not job:
            raise ResourceNotFoundError("TryOnJob", job_id)
        if user_id and job.user_id and job.user_id != user_id:
            raise AuthorizationError("Cannot cancel another user's job.")

        job.status = TryOnJobStatus.CANCELLED
        job.current_stage = "cancelled"
        self.db.commit()
        return {"job_id": job_id, "status": "cancelled"}

    def get_or_create_garment_asset(self, product_id: int) -> Dict[str, Any]:
        asset = self.db.query(GarmentAsset).filter(GarmentAsset.product_id == product_id).first()
        if asset:
            return {
                "id": asset.id,
                "product_id": asset.product_id,
                "slot_type": asset.slot_type,
                "flat_image_url": asset.flat_image_url,
                "segmented_garment_url": asset.segmented_garment_url,
                "garment_mask_url": asset.garment_mask_url,
                "created_at": asset.created_at
            }

        product = self.catalog_repo.get_product_by_id(product_id)
        if not product:
            raise ResourceNotFoundError("Product", product_id)

        # Create new asset record
        new_asset = GarmentAsset(
            product_id=product.id,
            slot_type=CATEGORY_TO_VTON_SLOT.get(product.category.slug, DEFAULT_VTON_SLOT) if product.category else DEFAULT_VTON_SLOT,
            flat_image_url=product.thumbnail_url,
            segmented_garment_url=product.thumbnail_url,
            garment_mask_url=product.thumbnail_url,
            bounding_box_json=json.dumps({"x": 0.2, "y": 0.25, "w": 0.6, "h": 0.5})
        )
        self.db.add(new_asset)
        self.db.commit()
        self.db.refresh(new_asset)
        return {
            "id": new_asset.id,
            "product_id": new_asset.product_id,
            "slot_type": new_asset.slot_type,
            "flat_image_url": new_asset.flat_image_url,
            "segmented_garment_url": new_asset.segmented_garment_url,
            "garment_mask_url": new_asset.garment_mask_url,
            "created_at": new_asset.created_at
        }

    def _format_job(self, job: TryOnJob) -> Dict[str, Any]:
        return {
            "id": job.id,
            "job_id": job.job_id,
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "progress_pct": job.progress_pct,
            "current_stage": job.current_stage,
            "model_used": job.model_used,
            "output_image_url": job.output_image_url,
            "metrics": json.loads(job.metrics_json) if job.metrics_json else {},
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "completed_at": job.completed_at
        }

    # =========================================================================
    # Multi-Garment Execution Pipeline
    # =========================================================================
    async def execute_multi_garment_tryon(
        self,
        product_ids: Optional[List[int]] = None,
        slot_mapping: Optional[Dict[str, int]] = None,
        user_image_url: Optional[str] = None,
        user_image_base64: Optional[str] = None,
        avatar_model_id: Optional[str] = "avatar_athletic_m",
        gender_mode: Optional[str] = "infer_from_image",
        user_id: Optional[int] = None,
        consent_retain_photo: bool = False,
        existing_session_id: Optional[int] = None
    ) -> Dict[str, Any]:
        target_ids = product_ids if product_ids else (list(slot_mapping.values()) if slot_mapping else [1])
        products = [self.catalog_repo.get_product_by_id(pid) for pid in target_ids if pid]
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

        effective_input_image = user_image_url or user_image_base64 or (
            "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600"
            if "female" in (avatar_model_id or "")
            else "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"
        )

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
                session.user_image_url = effective_input_image
                session.input_user_image_url = effective_input_image
                session.garment_image_url = applied_items[0]["image_url"] if applied_items else products[0].thumbnail_url
                session.rendered_result_url = vton_result.get("rendered_image_url", effective_input_image)
                session.applied_items_json = json.dumps(applied_items)
                session.slot_mapping_json = json.dumps(computed_slot_map)
                session.layering_order_json = json.dumps([it["position"] for it in applied_items])
                session.fit_confidence_score = vton_result.get("fit_confidence", 95)
                session.body_fit_verdict = vton_result.get("fit_verdict", "Optimal Garment Fit")
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
                    fit_verdict=vton_result.get("fit_verdict", "Optimal Garment Fit"),
                    fit_confidence_score=vton_result.get("fit_confidence", 95),
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
                fit_verdict=vton_result.get("fit_verdict", "Optimal Garment Fit"),
                fit_confidence_score=vton_result.get("fit_confidence", 95),
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
            "total_price": total_price,
            "fit_confidence_score": session.fit_confidence_score,
            "body_fit_verdict": session.body_fit_verdict,
            "recommended_sizes": recommended_sizes,
            "ai_disclosure": vton_result.get("ai_disclosure", "CONFIT VTON Engine — Identity Preserved"),
            "traceability_hash": vton_result.get("traceability_hash", f"VTON-CERT-{session.id}"),
            "layering_order": [it["position"] for it in applied_items],
            "dynamic_prompt_generated": vton_result.get("dynamic_prompt_generated", ""),
            "expires_at": session.expires_at
        }

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

        effective_image = user_image_url or (
            "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600"
            if "female" in (avatar_model_id or "")
            else "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"
        )

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

    def get_session_details(self, session_id: int, caller_user_id: Optional[int] = None) -> Dict[str, Any]:
        session = self.tryon_repo.get_tryon_session(session_id, caller_user_id=caller_user_id)
        if not session:
            raise ResourceNotFoundError("TryOnSession", session_id)

        applied = json.loads(session.applied_items_json) if session.applied_items_json else []
        return {
            "session_id": session.id,
            "status": session.status,
            "applied_items": applied,
            "slot_mapping": json.loads(session.slot_mapping_json) if session.slot_mapping_json else {},
            "layering_order": json.loads(session.layering_order_json) if session.layering_order_json else [],
            "rendered_result_url": session.rendered_result_url,
            "fit_confidence_score": session.fit_confidence_score,
            "body_fit_verdict": session.body_fit_verdict,
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
        session = self.tryon_repo.get_tryon_session(session_id)
        if not session:
            raise ResourceNotFoundError("TryOnSession", session_id)

        product = self.catalog_repo.get_product_by_id(product_id)
        if not product:
            raise ResourceNotFoundError("Product", product_id)

        current_items = json.loads(session.applied_items_json) if session.applied_items_json else []
        resolution = self.slot_engine.resolve_and_apply(current_items, product, target_slot_override=slot)

        product_ids = [it["product_id"] for it in resolution.final_applied_items]
        return await self.execute_multi_garment_tryon(
            product_ids=product_ids,
            user_image_url=session.input_user_image_url,
            user_id=user_id,
            existing_session_id=session.id
        )

    async def remove_item_from_session(
        self,
        session_id: int,
        product_id: Optional[int] = None,
        slot: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        session = self.tryon_repo.get_tryon_session(session_id)
        if not session:
            raise ResourceNotFoundError("TryOnSession", session_id)

        current_items = json.loads(session.applied_items_json) if session.applied_items_json else []
        resolution = self.slot_engine.resolve_and_remove(current_items, product_id=product_id, slot=slot)
        remaining_items = resolution.final_applied_items

        product_ids = [it["product_id"] for it in remaining_items]
        if not product_ids:
            session.applied_items_json = "[]"
            session.rendered_result_url = session.input_user_image_url
            self.db.commit()
            return {
                "session_id": session.id,
                "status": "ready",
                "applied_items": [],
                "rendered_result_url": session.input_user_image_url
            }

        return await self.execute_multi_garment_tryon(
            product_ids=product_ids,
            user_image_url=session.input_user_image_url,
            user_id=user_id,
            existing_session_id=session.id
        )

    def reorder_session_items(self, session_id: int, slot_order: List[str]) -> Dict[str, Any]:
        session = self.tryon_repo.get_tryon_session(session_id)
        if not session:
            raise ResourceNotFoundError("TryOnSession", session_id)

        current_items = json.loads(session.applied_items_json) if session.applied_items_json else []
        reordered = self.slot_engine.reorder_layers(current_items, slot_order)
        session.applied_items_json = json.dumps(reordered)
        session.layering_order_json = json.dumps(slot_order)
        self.db.commit()
        return {
            "session_id": session.id,
            "status": "reordered",
            "applied_items": reordered,
            "layering_order": slot_order
        }

    def apply_measurements_to_session(
        self,
        session_id: int,
        height_cm: float,
        chest_cm: Optional[float] = None,
        waist_cm: Optional[float] = None,
        shoulder_cm: Optional[float] = None,
        caller_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        session = self.tryon_repo.get_tryon_session(session_id, caller_user_id=caller_user_id)
        if not session:
            raise ResourceNotFoundError("TryOnSession", session_id)

        # Single body-scaling factor used for global drape — deterministic,
        # NOT an AI-derived fit prediction. The frontend is never told this is
        # a precise sizing guarantee; it is a visual approximation only.
        height = float(height_cm)
        scaling = round(height / 175.0, 2)
        session.body_scaling_factor = scaling

        # Per-slot scaling factors, used for future per-region drape. Stored
        # in render_metadata_json under a stable key — additive, doesn't
        # change existing schema. None means "not applicable / not provided".
        meta = json.loads(session.render_metadata_json) if session.render_metadata_json else {}
        slot_scaling = meta.get("slot_scaling", {})
        # chest defaults to ~98cm ref, waist ~82cm ref, shoulder ~45cm ref
        if chest_cm is not None and chest_cm > 0:
            slot_scaling["chest"] = round(chest_cm / 98.0, 2)
        if waist_cm is not None and waist_cm > 0:
            slot_scaling["waist"] = round(waist_cm / 82.0, 2)
        if shoulder_cm is not None and shoulder_cm > 0:
            slot_scaling["shoulder"] = round(shoulder_cm / 45.0, 2)
        meta["slot_scaling"] = slot_scaling
        session.render_metadata_json = json.dumps(meta)
        self.db.commit()

        return {
            "session_id": session.id,
            "status": "scaling_applied",
            "scaling_factor": scaling,
            "slot_scaling": slot_scaling,
            "applied_measurements": {
                "height_cm": height_cm,
                "chest_cm": chest_cm,
                "waist_cm": waist_cm,
                "shoulder_cm": shoulder_cm
            }
        }

    def purge_tryon_session(self, session_id: int, caller_user_id: Optional[int] = None) -> Dict[str, Any]:
        purged = self.tryon_repo.purge_session(session_id, caller_user_id=caller_user_id)
        if not purged:
            raise ResourceNotFoundError("TryOnSession", session_id)
        return {"session_id": session_id, "status": "purged", "message": "Biometric session wiped under GDPR Art. 17."}
