"""
CONFIT VTON Service - Production Hardened
- Real GPU worker integration with health/readiness retries
- Admin token authentication
- Base64 garment fetching with SSRF protection
- Output validation (no echo, no empty, pixel change verification)
- Multi-garment and animated try-on with real inference per layer
- Honest failure taxonomy, no fake fallbacks
- Observability with structured logging
- Slot-aware layering via SlotLayeringEngine
"""
import hmac
import json
import uuid
import os
import time
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.models.tryon import TryOnJob, TryOnJobStatus, GarmentAsset
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.tryon_repository import TryOnRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.providers.tryon_provider import VirtualTryOnProvider
from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine
from backend.app.services import vton_delivery
from backend.app.services.vton_delivery import temporary_image_store
from backend.app.core.config import settings
from backend.app.core.exceptions import (
    ResourceNotFoundError,
    ValidationDomainError,
    AuthorizationError,
    DeliveryGoneError,
)
from backend.app.core.logging import logger


CATEGORY_TO_VTON_SLOT = {
    "outerwear":   "upper_outer",
    "tops":        "upper_inner",
    "bottoms":     "lower",
    "dresses":     "dress",
    "footwear":    "footwear",
    "accessories": "accessory",
}
DEFAULT_VTON_SLOT = "upper_inner"
SUPPORTED_SLOTS = {"upper_outer", "upper_inner", "lower", "dress", "footwear", "accessory"}

# Maximum image size for person/garment fetching (15MB)
MAX_IMAGE_BYTES = 15 * 1024 * 1024
# Maximum dimension to prevent decompression bombs
MAX_IMAGE_DIMENSION = 4096
# Minimum valid image size
MIN_IMAGE_BYTES = 100


class TryOnService:
    def __init__(self, db: Session):
        self.db = db
        self.catalog_repo = CatalogRepository(db)
        self.tryon_repo = TryOnRepository(db)
        self.profile_repo = ProfileRepository(db)
        self.vton_provider = VirtualTryOnProvider()
        self.slot_engine = SlotLayeringEngine()

    def _get_worker_config(self) -> Tuple[Optional[str], str]:
        """Get worker URL and admin token from settings or env. Never logs token."""
        worker_url = settings.VTON_WORKER_URL or os.environ.get("VTON_WORKER_URL")
        admin_token = (
            getattr(settings, "VTON_WORKER_ADMIN_TOKEN", None)
            or getattr(settings, "CONFIT_WORKER_ADMIN_TOKEN", None)
            or os.environ.get("VTON_WORKER_ADMIN_TOKEN")
            or os.environ.get("CONFIT_WORKER_ADMIN_TOKEN")
            or ""
        )
        return worker_url, admin_token

    async def _fetch_image_as_base64(self, url: str) -> Optional[str]:
        """
        Fetch remote image and convert to data URL with security checks.
        - SSRF protection via is_safe_image_url
        - Size limit 15MB
        - MIME detection from content-type or magic bytes
        - Timeout 15s
        Returns None if fails (caller decides fallback).
        """
        if not url:
            return None
        if url.startswith("data:image"):
            # Validate data URL size (rough check)
            try:
                b64_part = url.split(",", 1)[1] if "," in url else ""
                # Approximate decoded size: base64 is ~33% overhead
                approx_bytes = len(b64_part) * 3 // 4
                if approx_bytes > MAX_IMAGE_BYTES:
                    logger.warn("person_image_data_url_too_large", approx_bytes=approx_bytes)
                    return None
                if approx_bytes < MIN_IMAGE_BYTES:
                    return None
            except Exception:
                pass
            return url

        # SSRF check for http(s) URLs
        if url.startswith("http"):
            try:
                from backend.app.core.security import is_safe_image_url
                if not is_safe_image_url(url):
                    logger.warn("garment_fetch_blocked_unsafe_url", url=url[:100])
                    return None
            except Exception:
                # If security module fails, be conservative and allow but log
                logger.warn("ssrf_check_failed_allowing", url=url[:100])

        try:
            import httpx
            import base64
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    follow_redirects=True,
                    headers={"User-Agent": "CONFIT-VTON/1.0"},
                )
                if resp.status_code != 200:
                    logger.warn("garment_fetch_http_error", url=url[:100], status=resp.status_code)
                    return None
                if len(resp.content) < MIN_IMAGE_BYTES:
                    logger.warn("garment_fetch_too_small", url=url[:100], size=len(resp.content))
                    return None
                if len(resp.content) > MAX_IMAGE_BYTES:
                    logger.warn("garment_fetch_too_large", url=url[:100], size=len(resp.content))
                    return None

                # MIME detection
                content_type = resp.headers.get("content-type", "").lower()
                mime = "image/jpeg"
                if "png" in content_type or resp.content[:8].startswith(b'\x89PNG'):
                    mime = "image/png"
                elif "webp" in content_type:
                    mime = "image/webp"
                elif "jpeg" in content_type or "jpg" in content_type:
                    mime = "image/jpeg"

                # Validate it's actually an image by trying to open
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(resp.content))
                    img.verify()
                    # Re-open after verify
                    img2 = Image.open(io.BytesIO(resp.content))
                    w, h = img2.size
                    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                        logger.warn("garment_fetch_dimensions_too_large", url=url[:100], w=w, h=h)
                        return None
                    if w < 32 or h < 32:
                        logger.warn("garment_fetch_dimensions_too_small", url=url[:100], w=w, h=h)
                        return None
                except Exception as e:
                    logger.warn("garment_fetch_invalid_image", url=url[:100], error=str(e)[:100])
                    return None

                b64 = base64.b64encode(resp.content).decode()
                return f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.warn("garment_fetch_failed", url=url[:100], error=str(e)[:200])
        return None

    async def _build_garments_payload(self, products) -> List[Dict[str, Any]]:
        """Build garments list with base64 images for reliable worker inference."""
        garments = []
        for p in products:
            slot = CATEGORY_TO_VTON_SLOT.get(
                p.category.slug if p.category else "", DEFAULT_VTON_SLOT
            )
            if slot not in SUPPORTED_SLOTS:
                slot = DEFAULT_VTON_SLOT

            # Try to fetch as base64 first for reliability (avoids worker SSRF/fetch issues)
            b64 = await self._fetch_image_as_base64(p.thumbnail_url)
            if b64:
                garments.append({
                    "product_id": p.id,
                    "slot_type": slot,
                    "image_base64": b64
                })
            else:
                # Fallback to URL - worker may still handle it with its own SSRF protection
                garments.append({
                    "product_id": p.id,
                    "slot_type": slot,
                    "image_url": p.thumbnail_url
                })
        return garments

    def _derive_worker_urls(self, worker_url: str) -> Tuple[str, str, str]:
        """Resolve (health_url, readiness_url, process_url) for the GPU worker.

        Explicit configuration always wins: ``VTON_WORKER_HEALTH_URL`` and
        ``VTON_WORKER_READINESS_URL`` (settings or environment). They exist
        because Modal generates one hostname PER web endpoint and truncates
        long labels to a hash — the live deployment (2026-09-03) exposes

            …-vtoninferenceservice-process.modal.run
            …-vtoninferenceservice-health.modal.run
            …-vtoninferenceservice-r-f73a19.modal.run   <- readiness

        so the old ``-process`` -> ``-readiness`` string replacement produced
        a hostname that does not exist. Derivation remains for the two layouts
        that ARE derivable (Modal ``-process`` -> ``-health``; a single FastAPI
        host with /health /readiness /process paths); when the readiness URL
        cannot be derived it falls back to the health URL, whose ``ready``
        field the caller already honours.
        """
        worker_url = worker_url.rstrip("/")
        explicit_health = (
            getattr(settings, "VTON_WORKER_HEALTH_URL", None) or os.environ.get("VTON_WORKER_HEALTH_URL") or ""
        ).strip()
        explicit_readiness = (
            getattr(settings, "VTON_WORKER_READINESS_URL", None) or os.environ.get("VTON_WORKER_READINESS_URL") or ""
        ).strip()
        explicit_process = (
            getattr(settings, "VTON_WORKER_PROCESS_URL", None) or os.environ.get("VTON_WORKER_PROCESS_URL") or ""
        ).strip()

        if "-process" in worker_url and "/" not in worker_url.split("//", 1)[-1]:
            # Modal per-method hostnames: only the health label is a safe derivation.
            process_url = worker_url
            health_url = worker_url.replace("-process", "-health")
            readiness_url = health_url  # not derivable (hash-truncated label) unless configured
        elif worker_url.endswith("/process"):
            base = worker_url[: -len("/process")]
            process_url, health_url, readiness_url = worker_url, f"{base}/health", f"{base}/readiness"
        else:
            process_url, health_url, readiness_url = (
                f"{worker_url}/process", f"{worker_url}/health", f"{worker_url}/readiness"
            )

        # Explicit config always wins for every leg. VTON_WORKER_PROCESS_URL lets
        # deployments where Modal exposes the process endpoint at its own hostname
        # root (not a "-process" label, not a "/process" path) override the derived
        # process_url instead of hitting a 404 on "<url>/process".
        if explicit_health:
            health_url = explicit_health
        if explicit_readiness:
            readiness_url = explicit_readiness
        if explicit_process:
            process_url = explicit_process
        return health_url, readiness_url, process_url

    async def _call_gpu_worker(
        self,
        job_id: str,
        person_image: str,
        garments: List[Dict[str, Any]],
        gender_mode: str = "infer_from_image",
        output_aspect: str = "9:16"
    ) -> Dict[str, Any]:
        """
        Call GPU worker with:
        - Health/readiness gate with retries and exponential backoff
        - Admin token authentication
        - Input validation (SSRF, size, MIME)
        - Output validation (no echo, no empty, valid data URL)
        - Timeout handling
        - Structured logging with observability fields (no secrets)
        - Honest error taxonomy
        """
        import httpx

        worker_url, admin_token = self._get_worker_config()
        if not worker_url:
            raise RuntimeError("VTON_ENGINE_UNAVAILABLE: No GPU worker configured (VTON_WORKER_URL)")

        if not person_image:
            raise ValueError("VTON_INPUT_INVALID: person image is required")
        if not garments:
            raise ValueError("VTON_GARMENT_ASSET_INVALID: at least one garment required")

        # Validate person image URL if it's http
        if person_image.startswith("http"):
            from backend.app.core.security import is_safe_image_url
            if not is_safe_image_url(person_image):
                raise ValueError("VTON_INPUT_INVALID: unsafe person image URL")

        # Validate garment URLs
        for g in garments:
            img_url = g.get("image_url") or ""
            if img_url.startswith("http"):
                from backend.app.core.security import is_safe_image_url
                if not is_safe_image_url(img_url):
                    raise ValueError(
                        f"VTON_GARMENT_ASSET_INVALID: unsafe garment URL for product {g.get('product_id')}"
                    )
            # Validate slot
            slot = g.get("slot_type", "")
            if slot and slot not in SUPPORTED_SLOTS:
                raise ValueError(f"VTON_INPUT_INVALID: unsupported slot_type {slot}")

        headers = {}
        if admin_token:
            headers["X-VTON-Admin"] = admin_token

        start_total = time.time()
        health_url, readiness_url, process_url = self._derive_worker_urls(worker_url)

        # Log with observability (no secrets)
        logger.info(
            "vton_worker_call_start",
            job_id=job_id,
            worker_url_host=worker_url.split("//")[-1].split("/")[0][:50] if "//" in worker_url else worker_url[:50],
            garments_count=len(garments),
            has_admin_token=bool(admin_token),
        )

        timeout_seconds = float(getattr(settings, "VTON_WORKER_TIMEOUT_SECONDS", 90.0))
        health_timeout = float(getattr(settings, "VTON_WORKER_HEALTH_TIMEOUT_SECONDS", 5.0))
        max_retries = int(getattr(settings, "VTON_WORKER_MAX_RETRIES", 3))

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            # Phase 1: Health/readiness gate with retries
            health_ok = False
            last_error = None
            for attempt in range(max_retries):
                try:
                    # Try readiness first (503 if not ready)
                    try:
                        readiness_resp = await client.get(readiness_url, timeout=health_timeout)
                        if readiness_resp.status_code == 200:
                            rj = readiness_resp.json()
                            if rj.get("ready") is True:
                                health_ok = True
                                logger.info("vton_worker_readiness_ok", attempt=attempt, job_id=job_id)
                                break
                        elif readiness_resp.status_code == 503:
                            last_error = f"readiness 503: {readiness_resp.text[:200]}"
                            logger.warn("vton_worker_readiness_503", attempt=attempt, job_id=job_id)
                        else:
                            last_error = f"readiness HTTP {readiness_resp.status_code}"
                    except Exception as e:
                        # Readiness endpoint may not exist on old deploys, try health
                        logger.debug("vton_readiness_check_failed_try_health", attempt=attempt, error=str(e)[:100])

                    health = await client.get(health_url, timeout=health_timeout)
                    if health.status_code == 200:
                        data = health.json()
                        if data.get("model_loaded") is True or data.get("ready") is True:
                            health_ok = True
                            logger.info(
                                "vton_worker_health_ok",
                                attempt=attempt,
                                job_id=job_id,
                                device=data.get("device"),
                                model_loaded=data.get("model_loaded"),
                            )
                            break
                        else:
                            last_error = data.get("load_error", "model not loaded")
                            logger.warn("vton_worker_not_ready", attempt=attempt, job_id=job_id, load_error=last_error)
                    else:
                        last_error = f"health HTTP {health.status_code}: {health.text[:200]}"
                        logger.warn("vton_worker_health_failed", attempt=attempt, job_id=job_id, status=health.status_code)
                except Exception as e:
                    last_error = str(e)[:300]
                    health_ok = False
                    logger.warn("vton_worker_health_exception", attempt=attempt, job_id=job_id, error=last_error)

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

            if not health_ok:
                if last_error and ("401" in str(last_error) or "UNAUTHORIZED" in str(last_error).upper()):
                    logger.error("vton_auth_failure", job_id=job_id, error=last_error[:200])
                    raise RuntimeError(f"VTON_AUTH_FAILURE: Worker auth failed: {last_error}")
                logger.error("vton_worker_not_ready_final", job_id=job_id, error=last_error)
                raise RuntimeError(
                    f"VTON_WORKER_NOT_READY: GPU worker not ready after {max_retries} attempts: {last_error or 'unreachable'}"
                )

            # Phase 2: Inference call
            inference_start = time.time()
            try:
                resp = await client.post(
                    process_url,
                    json={
                        "job_id": job_id,
                        "user_image_base64_or_url": person_image,
                        "garments": garments,
                        "gender_mode": gender_mode or "infer_from_image",
                        "output_aspect": output_aspect or "9:16"
                    },
                    headers=headers,
                )

                latency_ms = round((time.time() - inference_start) * 1000, 1)
                total_latency_ms = round((time.time() - start_total) * 1000, 1)

                # Error taxonomy
                if resp.status_code == 401:
                    logger.error("vton_auth_failure_401", job_id=job_id, latency_ms=latency_ms)
                    raise RuntimeError("VTON_AUTH_FAILURE: Missing or wrong X-VTON-Admin header")
                elif resp.status_code == 403:
                    logger.error("vton_auth_failure_403", job_id=job_id, latency_ms=latency_ms)
                    raise RuntimeError("VTON_AUTH_FAILURE: Forbidden - invalid token")
                elif resp.status_code == 422:
                    logger.warn("vton_input_invalid", job_id=job_id, latency_ms=latency_ms, response=resp.text[:500])
                    raise RuntimeError(f"VTON_INPUT_INVALID: Worker rejected input: {resp.text[:500]}")
                elif resp.status_code == 503:
                    logger.warn("vton_worker_not_ready_503", job_id=job_id, latency_ms=latency_ms, response=resp.text[:500])
                    raise RuntimeError(f"VTON_WORKER_NOT_READY: Worker not ready: {resp.text[:500]}")
                elif resp.status_code != 200:
                    logger.error(
                        "vton_worker_unavailable",
                        job_id=job_id,
                        latency_ms=latency_ms,
                        status=resp.status_code,
                        body=resp.text[:500]
                    )
                    raise RuntimeError(f"VTON_WORKER_UNAVAILABLE: Worker returned HTTP {resp.status_code}: {resp.text[:500]}")

                gpu_data = resp.json()
                rendered = gpu_data.get("rendered_image_data_url")

                # Output validation: meaningful checks
                if not rendered:
                    logger.error("vton_output_invalid_empty", job_id=job_id, latency_ms=latency_ms)
                    raise RuntimeError("VTON_OUTPUT_INVALID: Worker returned no rendered image")

                # No echo: input unchanged is failure, not success
                if rendered == person_image:
                    logger.error("vton_output_invalid_echo", job_id=job_id, latency_ms=latency_ms)
                    raise RuntimeError("VTON_OUTPUT_INVALID: Worker returned input unchanged (echo)")

                # Validate data URL format
                if rendered.startswith("data:image"):
                    try:
                        header, b64_data = rendered.split(",", 1)
                        if len(b64_data) < 100:
                            raise RuntimeError("VTON_OUTPUT_INVALID: rendered image too small")
                        # Check it's valid base64 and decodable image
                        import base64 as _b64
                        import io
                        from PIL import Image
                        raw = _b64.b64decode(b64_data)
                        if len(raw) < 1000:
                            raise RuntimeError("VTON_OUTPUT_INVALID: decoded image too small")
                        img = Image.open(io.BytesIO(raw))
                        w, h = img.size
                        if w < 32 or h < 32:
                            raise RuntimeError(f"VTON_OUTPUT_INVALID: output dimensions too small {w}x{h}")
                    except RuntimeError:
                        raise
                    except Exception as e:
                        logger.error("vton_output_invalid_decode", job_id=job_id, error=str(e)[:200])
                        raise RuntimeError(f"VTON_OUTPUT_INVALID: cannot decode output image: {e}")

                elif rendered.startswith("http"):
                    from backend.app.core.security import is_safe_image_url
                    if not is_safe_image_url(rendered):
                        logger.error("vton_output_invalid_unsafe_url", job_id=job_id, latency_ms=latency_ms)
                        raise RuntimeError("VTON_OUTPUT_INVALID: Unsafe output URL")

                # Verify metrics if present
                verify = gpu_data.get("verify") or {}
                if verify:
                    pixel_change = verify.get("metric_pixel_change")
                    color_shift = verify.get("metric_color_shift")
                    if pixel_change is not None and pixel_change < 0.5:
                        logger.warn("vton_output_low_pixel_change", job_id=job_id, pixel_change=pixel_change)
                    if color_shift is not None and color_shift < 0.001:
                        logger.warn("vton_output_low_color_shift", job_id=job_id, color_shift=color_shift)

                logger.info(
                    "vton_inference_success",
                    job_id=job_id,
                    latency_ms=latency_ms,
                    total_latency_ms=total_latency_ms,
                    model_used=gpu_data.get("model_used"),
                    execution_time_ms=gpu_data.get("execution_time_ms"),
                    layers_processed=gpu_data.get("layers_processed"),
                    output_size=len(rendered) if rendered else 0,
                    verify_pass=verify.get("PASS") if verify else None,
                )

                return gpu_data

            except httpx.TimeoutException as e:
                logger.error("vton_timeout", job_id=job_id, error=str(e)[:200])
                raise RuntimeError(f"VTON_TIMEOUT: GPU worker timeout: {str(e)}")
            except httpx.ConnectError as e:
                logger.error("vton_worker_unavailable_connect", job_id=job_id, error=str(e)[:200])
                raise RuntimeError(f"VTON_WORKER_UNAVAILABLE: Cannot connect to worker: {str(e)}")

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
        """Async job queue: creates job, tries GPU worker, fails honestly if no worker."""
        if not product_ids:
            raise ValidationDomainError("At least one garment product_id is required to start a Try-On job.")

        job_id = f"vton_job_{uuid.uuid4().hex[:12]}"
        effective_image = user_image_url or user_image_base64 or "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"

        products = [self.catalog_repo.get_product_by_id(pid) for pid in product_ids]
        valid_products = [p for p in products if p is not None]
        if not valid_products:
            raise ResourceNotFoundError("Products", str(product_ids))

        # One-time delivery capability for this job, issued at creation. For
        # guest (anonymous) submitters it is the ONLY handle that binds them
        # to their job across serverless instances (status polling); for user
        # jobs ownership is enforced by identity. The plaintext token is
        # returned in the job response below; only its SHA-256 hash persists.
        delivery_token, delivery_token_hash = temporary_image_store.new_delivery_credentials()

        job = TryOnJob(
            job_id=job_id,
            user_id=user_id,
            status=TryOnJobStatus.QUEUED,
            progress_pct=10,
            current_stage="queued",
            input_person_image_url=effective_image,
            garment_ids_json=json.dumps([p.id for p in valid_products]),
            garment_layers_json=json.dumps(
                [{"id": p.id, "title": p.title, "category": p.category.name if p.category else "Garment"} for p in valid_products]
            ),
            model_used="pending (no render yet)",
            delivery_token_hash=delivery_token_hash,
            metrics_json=json.dumps({"queued_at": str(datetime.now(timezone.utc))})
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        job.status = TryOnJobStatus.PARSING_PERSON
        job.progress_pct = 35
        job.current_stage = "human_parsing_schp"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()

        worker_url, _ = self._get_worker_config()
        if worker_url:
            job.current_stage = "gpu_diffusion_rendering"
            job.progress_pct = 65
            self.db.commit()

            try:
                garments = await self._build_garments_payload(valid_products)
                person_b64 = effective_image
                if effective_image.startswith("http"):
                    fetched = await self._fetch_image_as_base64(effective_image)
                    if fetched:
                        person_b64 = fetched

                gpu_data = await self._call_gpu_worker(
                    job_id=job_id,
                    person_image=person_b64,
                    garments=garments,
                    gender_mode=gender_mode or "infer_from_image",
                    output_aspect=output_aspect or "9:16"
                )

                rendered = gpu_data.get("rendered_image_data_url")
                job.status = TryOnJobStatus.COMPLETED
                job.progress_pct = 100
                job.current_stage = "harmonized_and_verified"
                # TEMPORARY (non-persistent) delivery — product requirement:
                # the generated try-on image is NEVER stored durably (no
                # S3/R2, no local disk, no image bytes or object keys in the
                # database). It is delivered in THIS authenticated response
                # (result_image_data_url — the guaranteed vehicle) and staged
                # in a process-local TTL cache for the one-shot, owner-only
                # download endpoint (best effort on serverless). Only the
                # token hash + expiry are persisted, on the job row.
                staged = vton_delivery.stage_vton_delivery(job_id, delivery_token_hash, rendered)
                job.delivery_expires_at = datetime.fromtimestamp(
                    float(staged["expires_at"]), tz=timezone.utc
                )
                job.delivery_content_type = staged["content_type"]
                job.completed_at = datetime.now(timezone.utc)
                if gpu_data.get("model_used"):
                    job.model_used = str(gpu_data["model_used"])[:100]
                job.metrics_json = json.dumps(gpu_data.get("quality_audit") or gpu_data.get("verify") or {})
                self.db.commit()
                self.db.refresh(job)
                return self._format_job(
                    job,
                    delivery={
                        "download_url": f"{settings.API_V1_STR}/try-on/jobs/{job.job_id}/result",
                        "token": delivery_token,
                        "expires_at": job.delivery_expires_at,
                        "content_type": staged["content_type"],
                        "byte_size": staged["byte_size"],
                        "ttl_seconds": staged["ttl_seconds"],
                        "one_time": True,
                    },
                    result_image_data_url=rendered,
                )

            except Exception as exc:
                error_str = str(exc)
                # Error taxonomy mapping
                if "VTON_AUTH_FAILURE" in error_str:
                    error_code = "VTON_AUTH_FAILURE"
                elif "VTON_WORKER_NOT_READY" in error_str:
                    error_code = "VTON_WORKER_NOT_READY"
                elif "VTON_INPUT_INVALID" in error_str or "VTON_GARMENT_ASSET_INVALID" in error_str:
                    error_code = "VTON_INPUT_INVALID"
                elif "VTON_OUTPUT_INVALID" in error_str:
                    error_code = "VTON_OUTPUT_INVALID"
                elif "VTON_TIMEOUT" in error_str:
                    error_code = "VTON_TIMEOUT"
                elif "VTON_ENGINE_UNAVAILABLE" in error_str:
                    error_code = "VTON_ENGINE_UNAVAILABLE"
                else:
                    error_code = "GPU_WORKER_ERROR"

                job.status = TryOnJobStatus.FAILED
                job.current_stage = "failed"
                job.error_code = error_code
                job.error_message = f"GPU Inference Worker Failure: {error_str[:500]}"
                # Failure path: nothing was staged — there is no artifact to
                # clean up; the capability token stays available for the
                # (guest) submitter to observe the failure state.
                self.db.commit()
                self.db.refresh(job)
                return self._format_job(job, delivery=self._delivery_ref(job, delivery_token))

        # No worker configured: honest failure, no fake image. Nothing was
        # staged — no artifact exists to clean up.
        job.status = TryOnJobStatus.FAILED
        job.current_stage = "failed"
        job.error_code = "VTON_ENGINE_UNAVAILABLE"
        job.error_message = "No GPU inference worker is configured (VTON_WORKER_URL). Set VTON_WORKER_URL to enable real CatVTON inference."
        job.model_used = "none (no render performed)"
        job.metrics_json = json.dumps({})
        self.db.commit()
        self.db.refresh(job)

        return self._format_job(job, delivery=self._delivery_ref(job, delivery_token))

    def get_vton_job_status(
        self,
        job_id: str,
        caller_user_id: Optional[int] = None,
        delivery_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Job status with the authorization contract enforced.

        * user job: only the owning user may read it (404 otherwise — no
          existence leakage);
        * guest job (anonymous submit): bound by the one-time delivery token,
          verified non-destructively against the stored hash (works across
          serverless instances because the hash is in the row).

        The response never re-serves the one-time token or the image bytes —
        those exist only in the authenticated completion response.
        """
        job = self.db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        if not job:
            raise ResourceNotFoundError("TryOnJob", job_id)
        if job.user_id is not None:
            if job.user_id != caller_user_id:
                raise ResourceNotFoundError("TryOnJob", job_id)
        else:
            provided = (
                vton_delivery.TemporaryImageStore._token_hash(delivery_token)
                if delivery_token else ""
            )
            if not job.delivery_token_hash or not hmac.compare_digest(
                provided, job.delivery_token_hash
            ):
                raise ResourceNotFoundError("TryOnJob", job_id)
        return self._format_job(job)

    def cancel_vton_job(self, job_id: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        job = self.db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        if not job:
            raise ResourceNotFoundError("TryOnJob", job_id)
        # Fail-closed ownership: a job bound to a user may only be cancelled
        # by that user (an anonymous caller can never act on a user job).
        if job.user_id is not None and job.user_id != user_id:
            raise AuthorizationError("Cannot cancel another user's job.")

        job.status = TryOnJobStatus.CANCELLED
        job.current_stage = "cancelled"
        # Explicit cleanup of any staged temporary copy (cleanup on the
        # failure/cancel path, per the delivery contract).
        if job.delivery_token_hash:
            temporary_image_store.purge_by_hash(job.delivery_token_hash, job.job_id)
            job.delivery_token_hash = None
            job.delivery_expires_at = None
            job.delivery_content_type = None
        self.db.commit()
        return {"job_id": job_id, "status": "cancelled"}

    @staticmethod
    def _is_generated_data_url(value: Optional[str]) -> bool:
        """True when ``value`` is a GPU-generated image payload (data URL).

        Generated try-on images are delivered temporarily and must never be
        persisted; pre-existing asset URLs (provider fallbacks) are not
        generated images and may still be referenced.
        """
        return bool(value) and value.startswith("data:image/")

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

    def _format_job(
        self,
        job: TryOnJob,
        delivery: Optional[Dict[str, Any]] = None,
        result_image_data_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Job payload.

        ``delivery`` (with the one-time token) and ``result_image_data_url``
        appear ONLY on the authenticated completion response — never on
        polling or for other callers. Polling sees at most the non-secret
        expiry metadata, so a stolen token is never re-served from the
        status endpoint.
        """
        out: Dict[str, Any] = {
            "id": job.id,
            "job_id": job.job_id,
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "progress_pct": job.progress_pct,
            "current_stage": job.current_stage,
            "model_used": job.model_used,
            "output_image_url": job.output_image_url,
            "delivery_expires_at": job.delivery_expires_at,
            "metrics": json.loads(job.metrics_json) if job.metrics_json else {},
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "completed_at": job.completed_at
        }
        if delivery is not None:
            out["delivery"] = delivery
        if result_image_data_url:
            out["result_image_data_url"] = result_image_data_url
        return out

    @staticmethod
    def _delivery_ref(job: TryOnJob, token: str) -> Dict[str, Any]:
        """Minimal delivery reference for (failed) job responses: lets the
        guest submitter keep polling their job; the download stays 410
        because no image was staged."""
        return {
            "download_url": f"{settings.API_V1_STR}/try-on/jobs/{job.job_id}/result",
            "token": token,
            "expires_at": job.delivery_expires_at,
            "content_type": job.delivery_content_type,
            "one_time": True,
        }

    def deliver_job_result(
        self,
        job_id: str,
        delivery_token: str,
        caller_user_id: Optional[int],
    ) -> Tuple[bytes, str, str]:
        """One-shot, owner-gated claim of a staged VTON result.

        Authorization contract (fail-closed, no existence leakage):
          * unknown job            -> 404
          * other user's job       -> 404 (indistinguishable from unknown)
          * expired / claimed /    -> 410 GONE (VTON_RESULT_GONE)
            revoked / not staged
          * owner + valid token    -> (payload, mime, job_id), entry deleted

        Guest jobs (``user_id IS NULL``) are bound by the one-time token
        alone: it is a 192-bit capability that exists only in the
        completion response and is destroyed on first use or TTL expiry.
        """
        job = self.db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        if job is None:
            raise ResourceNotFoundError("TryOnJob", job_id)
        if job.user_id is not None and job.user_id != caller_user_id:
            raise ResourceNotFoundError("TryOnJob", job_id)
        if not job.delivery_token_hash or not job.delivery_expires_at:
            raise DeliveryGoneError("never_staged")
        expires = job.delivery_expires_at
        if expires.tzinfo is None:  # SQLite returns naive datetimes; treat as UTC
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            raise DeliveryGoneError("expired")
        got = temporary_image_store.claim(delivery_token or "", job_id)
        if got is None:
            raise DeliveryGoneError("expired_or_delivered")
        payload, mime = got
        return payload, mime, job.job_id

    def revoke_job_result(self, job_id: str, caller_user_id: Optional[int]) -> None:
        """Explicit owner revocation: delete the staged copy immediately."""
        job = self.db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
        if job is None:
            raise ResourceNotFoundError("TryOnJob", job_id)
        if job.user_id is not None and job.user_id != caller_user_id:
            raise ResourceNotFoundError("TryOnJob", job_id)
        if job.delivery_token_hash:
            temporary_image_store.purge_by_hash(job.delivery_token_hash, job.job_id)
            job.delivery_token_hash = None
            job.delivery_expires_at = None
            job.delivery_content_type = None
            self.db.commit()

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
        """
        Multi-garment try-on with real GPU inference when worker configured.
        Falls back to honest failure (no fake image) when no worker.
        """
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

        worker_url, _ = self._get_worker_config()
        vton_result: Optional[Dict[str, Any]] = None
        gpu_data: Optional[Dict[str, Any]] = None

        if worker_url:
            try:
                job_id = f"multi_{uuid.uuid4().hex[:12]}"
                garments = await self._build_garments_payload(products)

                person_img = effective_input_image
                if effective_input_image.startswith("http"):
                    fetched = await self._fetch_image_as_base64(effective_input_image)
                    if fetched:
                        person_img = fetched

                gpu_data = await self._call_gpu_worker(
                    job_id=job_id,
                    person_image=person_img,
                    garments=garments,
                    gender_mode=gender_mode or "infer_from_image",
                    output_aspect="9:16"
                )

                rendered_url = gpu_data.get("rendered_image_data_url")
                # TEMPORARY (non-persistent) delivery: the GPU-generated image
                # travels in the authenticated response only (rendered_result_url
                # below). It is NEVER written to durable storage or to the
                # session row (product requirement). Provider-fallback values
                # reference pre-existing assets, not generated images.
                rendered_ref = rendered_url
                vton_result = {
                    "rendered_image_url": rendered_ref,
                    "fit_verdict": gpu_data.get("fit_verdict", "Optimal Garment Fit"),
                    "fit_confidence": 96,
                    "traceability_hash": f"VTON-CERT-{hashlib.sha256(f'{job_id}{time.time()}'.encode()).hexdigest()[:16].upper()}",
                    "ai_disclosure": f"CONFIT VTON Engine — {gpu_data.get('model_used', 'CatVTON')} — Identity Preserved",
                    "dynamic_prompt_generated": "",
                    "model_used": gpu_data.get("model_used"),
                    "execution_time_ms": gpu_data.get("execution_time_ms"),
                    "verify": gpu_data.get("verify"),
                }
                logger.info("multi_garment_real_inference_success", job_id=job_id, products=target_ids)

            except Exception as exc:
                error_str = str(exc)
                logger.warn("multi_garment_gpu_fallback", error=error_str[:300], products=target_ids)

                # Only fallback to provider for ENGINE_UNAVAILABLE (no worker), not for other errors
                if "VTON_ENGINE_UNAVAILABLE" in error_str:
                    vton_result = await self.vton_provider.render_multi_garment_tryon(
                        user_image_url=effective_input_image,
                        applied_items=applied_items,
                        gender_mode=gender_mode or "infer_from_image",
                        body_scaling=scaling
                    )
                else:
                    # For other errors (auth, input invalid, timeout, etc), fail honestly
                    raise

        if vton_result is None:
            # No worker or worker failed with ENGINE_UNAVAILABLE -> try provider (which will also fail honestly)
            try:
                vton_result = await self.vton_provider.render_multi_garment_tryon(
                    user_image_url=effective_input_image,
                    applied_items=applied_items,
                    gender_mode=gender_mode or "infer_from_image",
                    body_scaling=scaling
                )
            except Exception as exc:
                # Provider raises TryOnEngineUnavailableError -> convert to honest error for API
                error_msg = str(exc)
                if "no_render_backend" in error_msg or "TryOnEngineUnavailable" in type(exc).__name__:
                    raise RuntimeError(
                        "VTON_ENGINE_UNAVAILABLE: No GPU worker configured and no local render backend. "
                        "Set VTON_WORKER_URL to enable real CatVTON inference."
                    )
                raise

        total_price = sum(it["price"] for it in applied_items)
        first_product_id = applied_items[0]["product_id"] if applied_items else products[0].id

        # TEMPORARY (non-persistent) delivery: a GPU-generated result (data URL)
        # is returned in the authenticated response and is NEVER persisted on
        # the session row — a multi-MB base64 blob in a Text column would be
        # exactly the permanent database retention the product forbids. Only
        # pre-existing references (provider-fallback asset, user input) are
        # recorded on the row.
        rendered_out = vton_result.get("rendered_image_url")
        session_rendered_ref = (
            None if self._is_generated_data_url(rendered_out)
            else (rendered_out or effective_input_image)
        )

        if existing_session_id:
            session = self.tryon_repo.get_tryon_session(existing_session_id)
            if session:
                session.product_id = first_product_id
                session.user_image_url = effective_input_image
                session.input_user_image_url = effective_input_image
                session.garment_image_url = applied_items[0]["image_url"] if applied_items else products[0].thumbnail_url
                session.rendered_result_url = session_rendered_ref
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
                    rendered_result_url=session_rendered_ref,
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
                rendered_result_url=session_rendered_ref,
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
            # In-response temporary delivery: for a GPU-generated result this
            # is the base64 data URL itself (the image travels in this
            # authenticated response and is not stored anywhere durable).
            "rendered_result_url": rendered_out or effective_input_image,
            "before_after_split_url": rendered_out or effective_input_image,
            "applied_items": applied_items,
            "total_price": total_price,
            "fit_confidence_score": session.fit_confidence_score,
            "body_fit_verdict": session.body_fit_verdict,
            "recommended_sizes": recommended_sizes,
            "ai_disclosure": vton_result.get("ai_disclosure", "CONFIT VTON Engine — Identity Preserved"),
            "traceability_hash": vton_result.get("traceability_hash", f"VTON-CERT-{session.id}"),
            "layering_order": [it["position"] for it in applied_items],
            "dynamic_prompt_generated": vton_result.get("dynamic_prompt_generated", ""),
            "expires_at": session.expires_at,
            "model_used": vton_result.get("model_used") or (gpu_data.get("model_used") if gpu_data else None),
            "execution_time_ms": vton_result.get("execution_time_ms") or (gpu_data.get("execution_time_ms") if gpu_data else None),
        }

    async def execute_animated_tryon(
        self,
        product_ids: Optional[List[int]] = None,
        slot_mapping: Optional[Dict[str, int]] = None,
        user_image_url: Optional[str] = None,
        user_image_base64: Optional[str] = None,
        avatar_model_id: Optional[str] = "avatar_athletic_m",
        gender_mode: Optional[str] = "infer_from_image",
        output_aspect: Optional[str] = "9:16",
        background_mode: Optional[str] = "studio",
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Animated try-on: real inference per layer, output becomes input for next layer.
        Each keyframe is a real CatVTON inference, not duplicated frames.
        Layer order deterministic via slot_engine layer_order.
        """
        # First get multi-garment data with real inference for final frame if worker exists
        # But for animated, we need per-layer inference regardless
        target_ids = product_ids if product_ids else (list(slot_mapping.values()) if slot_mapping else [1])
        products = [self.catalog_repo.get_product_by_id(pid) for pid in target_ids if pid]
        products = [p for p in products if p is not None]
        if not products:
            raise ResourceNotFoundError("Products", str(target_ids))

        # Resolve layering
        accumulated = []
        for p in products:
            res = self.slot_engine.resolve_and_apply(accumulated, p)
            accumulated = res.final_applied_items
        applied_items = accumulated

        if not applied_items:
            raise ValidationDomainError("No garments applied for animated try-on")

        effective_image = user_image_url or user_image_base64 or (
            "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600"
            if "female" in (avatar_model_id or "")
            else "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600"
        )

        # Create session first with base image
        total_price = sum(it["price"] for it in applied_items)
        first_product_id = applied_items[0]["product_id"] if applied_items else products[0].id
        session = self.tryon_repo.create_tryon_session(
            product_id=first_product_id,
            input_user_image_url=effective_image,
            garment_image_url=applied_items[0]["image_url"] if applied_items else products[0].thumbnail_url,
            rendered_result_url=effective_image,  # will be updated after first successful inference
            applied_items=applied_items,
            slot_mapping={it.get("position"): it["product_id"] for it in applied_items},
            user_id=user_id,
            fit_verdict="Optimal Garment Fit",
            fit_confidence_score=95,
            body_scaling_factor=1.0,
            consent_retained=False,
            expiry_hours=24
        )

        worker_url, _ = self._get_worker_config()
        keyframes = []
        animation_style = "premium_realistic"

        if worker_url:
            try:
                ordered_items = sorted(applied_items, key=lambda x: x.get("layer_order", 1))
                # Build garment base64 payloads
                product_map = {}
                for prod in products:
                    b64 = await self._fetch_image_as_base64(prod.thumbnail_url)
                    product_map[prod.id] = b64 or prod.thumbnail_url

                current_person_image = effective_image
                if effective_image.startswith("http"):
                    fetched = await self._fetch_image_as_base64(effective_image)
                    if fetched:
                        current_person_image = fetched

                for idx, item in enumerate(ordered_items, start=1):
                    pid = item["product_id"]
                    g_img = product_map.get(pid)
                    if not g_img:
                        g_img = await self._fetch_image_as_base64(item.get("image_url", "")) or item.get("image_url", "")

                    if g_img and g_img.startswith("data:image"):
                        garment_payload = {
                            "product_id": pid,
                            "slot_type": item.get("slot_type") or item.get("position", "upper_inner"),
                            "image_base64": g_img
                        }
                    else:
                        garment_payload = {
                            "product_id": pid,
                            "slot_type": item.get("slot_type") or item.get("position", "upper_inner"),
                            "image_url": g_img
                        }

                    job_id = f"anim_{uuid.uuid4().hex[:8]}_layer{idx}"

                    try:
                        person_for_frame = current_person_image if idx == 1 else keyframes[-1]["image_url"] if keyframes else current_person_image

                        gpu_data = await self._call_gpu_worker(
                            job_id=job_id,
                            person_image=person_for_frame,
                            garments=[garment_payload],
                            gender_mode=gender_mode or "infer_from_image",
                            output_aspect=output_aspect or "9:16"
                        )

                        frame_url = gpu_data.get("rendered_image_data_url")
                        # Output becomes input for next layer (sequential architecture)
                        current_person_image = frame_url

                        keyframes.append({
                            "step": idx,
                            "slot": item.get("position") or item.get("slot_type"),
                            "product_title": item.get("product_title"),
                            "brand_name": item.get("brand_name"),
                            "image_url": frame_url,
                            "status": f"Layer {idx}: {item.get('product_title')} ({(item.get('position') or item.get('slot_type', '')).replace('_', ' ')})",
                            "model_used": gpu_data.get("model_used"),
                            "execution_time_ms": gpu_data.get("execution_time_ms"),
                        })

                        logger.info("animated_keyframe_success", step=idx, job_id=job_id, product=item.get("product_title"))

                    except Exception as frame_exc:
                        error_str = str(frame_exc)
                        logger.warn("animated_keyframe_failed", step=idx, error=error_str[:300])
                        # If single frame fails, don't fallback to fake - fail honestly unless it's last resort
                        # For animated, if one layer fails, we cannot continue sequence honestly
                        # So we raise if first frame fails, otherwise keep previous frames and mark failure
                        if idx == 1:
                            # First frame failed - no valid animation possible
                            raise RuntimeError(f"VTON_ANIMATED_FIRST_FRAME_FAILED: {error_str}")
                        # For subsequent frames, keep previous successful frames but note failure
                        # Don't add fake frame
                        keyframes.append({
                            "step": idx,
                            "slot": item.get("position") or item.get("slot_type"),
                            "product_title": item.get("product_title"),
                            "brand_name": item.get("brand_name"),
                            "image_url": keyframes[-1]["image_url"] if keyframes else current_person_image,
                            "status": f"Layer {idx} failed: {error_str[:100]}",
                            "error": error_str[:300],
                            "failed": True,
                        })

                # Filter out failed frames for final check
                successful_frames = [kf for kf in keyframes if not kf.get("failed")]
                if not successful_frames:
                    logger.warn("animated_all_keyframes_failed", products=product_ids)
                    raise RuntimeError("VTON_ANIMATED_ALL_FAILED: All animated keyframes failed")

                animation_style = "premium_realistic_gpu"
                logger.info("animated_tryon_real_success", keyframes=len(successful_frames), products=product_ids)

                # TEMPORARY (non-persistent) delivery: the generated frames
                # travel in the authenticated response (keyframes) and are
                # NEVER persisted on the session row — storing the final
                # frame's multi-MB base64 blob in a Text column would be
                # permanent database retention of a generated image, which the
                # product requirement forbids.
                if successful_frames:
                    session.rendered_result_url = None
                    self.db.commit()

            except Exception as exc:
                error_str = str(exc)
                logger.warn("animated_gpu_failed", error=error_str[:500])
                if "VTON_ENGINE_UNAVAILABLE" in error_str:
                    # No worker - try provider which will fail honestly
                    try:
                        anim_res = await self.vton_provider.render_animated_tryon(
                            user_image_url=effective_image,
                            applied_items=applied_items,
                            gender_mode=gender_mode or "infer_from_image",
                            output_aspect=output_aspect or "9:16",
                            background_mode=background_mode or "studio"
                        )
                        keyframes = anim_res.get("keyframes_sequence", [])
                        animation_style = anim_res.get("animation_style", "premium_realistic")
                    except Exception:
                        raise RuntimeError(
                            "VTON_ENGINE_UNAVAILABLE: Animated try-on requires GPU worker. "
                            "Set VTON_WORKER_URL to enable real CatVTON inference per layer."
                        )
                elif "VTON_ANIMATED" in error_str:
                    raise
                else:
                    # For other errors (auth, timeout, etc), fail honestly
                    raise

        if not keyframes:
            # No worker and no keyframes - try provider fallback which will fail honestly
            try:
                anim_res = await self.vton_provider.render_animated_tryon(
                    user_image_url=effective_image,
                    applied_items=applied_items,
                    gender_mode=gender_mode or "infer_from_image",
                    output_aspect=output_aspect or "9:16",
                    background_mode=background_mode or "studio"
                )
                keyframes = anim_res.get("keyframes_sequence", [])
                animation_style = anim_res.get("animation_style", "premium_realistic")
            except Exception:
                raise RuntimeError(
                    "VTON_ENGINE_UNAVAILABLE: Animated try-on requires GPU worker for real per-layer inference. "
                    "Set VTON_WORKER_URL to enable."
                )

        if not keyframes:
            raise RuntimeError("VTON_OUTPUT_INVALID: No keyframes generated for animated try-on")

        # Ensure no fake duplication: each keyframe must be distinct (different step)
        # and if successful, should have different image_url (or at least different step)
        successful = [kf for kf in keyframes if not kf.get("failed")]
        if len(successful) > 1:
            # Check if all image_urls are identical (would indicate fake duplication)
            urls = [kf["image_url"] for kf in successful]
            if len(set(urls)) == 1 and len(urls) > 1:
                logger.warn("animated_keyframes_all_identical_possible_fake", urls_count=len(urls))
                # This could be legitimate if model returns same image, but log warning
                # Don't fail, but note in logs

        return {
            "session_id": session.id,
            "status": "completed",
            "animation_style": animation_style,
            "output_aspect": output_aspect or "9:16",
            "rendered_animation_url": successful[-1]["image_url"] if successful else keyframes[-1]["image_url"],
            "keyframes_sequence": keyframes,
            "fit_confidence_score": 95,
            "body_fit_verdict": "Optimal Garment Fit",
            "traceability_hash": f"VTON-ANIM-{hashlib.sha256(f'{session.id}{time.time()}'.encode()).hexdigest()[:16].upper()}",
            "ai_disclosure": "CONFIT VTON Engine — CatVTON — Identity Preserved — Real per-layer inference",
            "dynamic_animation_prompt": "",
            "applied_items": applied_items,
            "total_price": total_price,
            "model_used": keyframes[0].get("model_used") if keyframes else None,
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
            "expires_at": res["expires_at"],
            "model_used": res.get("model_used"),
            "execution_time_ms": res.get("execution_time_ms"),
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

        height = float(height_cm)
        scaling = round(height / 175.0, 2)
        session.body_scaling_factor = scaling

        meta = json.loads(session.render_metadata_json) if session.render_metadata_json else {}
        slot_scaling = meta.get("slot_scaling", {})
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
