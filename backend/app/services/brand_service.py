import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.app.models.catalog import Product, ProductSKU, StoreLocation, StoreInventory
from backend.app.models.brand_analytics import SponsoredPlacement
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError, AuthorizationError
from backend.app.core.security import get_password_hash, verify_password
from backend.app.services.auth_service import AuthService


class BrandService:
    def __init__(self, db: Session):
        self.db = db
        self.brand_repo = BrandRepository(db)
        # Request-scoped memo. A BrandService is constructed per request (see the
        # Depends(get_db) wiring in brand_controller), so this cache lives and
        # dies with the request and can never serve one tenant's profile to
        # another. It exists because a single endpoint resolved the SAME
        # brand_profiles row up to three times -- once here, once through the
        # user.brand_profile lazy load in the ownership check, and once inside
        # the repository -- and against the managed database each of those cost
        # a full network round trip.
        self._brand_by_user: Dict[int, BrandProfile] = {}

    def _resolve_brand(self, user: User) -> BrandProfile:
        """Single place that turns an authenticated user into their tenant row."""
        cached = self._brand_by_user.get(user.id)
        if cached is not None:
            return cached
        bp = self.brand_repo.get_by_user_id(user.id)
        if not bp:
            raise AuthorizationError("No Brand Organization linked to this account. Request partner onboarding; administrators must use explicit admin routes.")
        self._brand_by_user[user.id] = bp
        return bp

    def get_brand_profile_by_user(self, user: User) -> Dict[str, Any]:
        """Resolves Brand Organization for the requesting user with strict tenant validation."""
        return self._format_brand(self._resolve_brand(user))

    def get_brand_analytics_dashboard(self, user: User, brand_id: int) -> Dict[str, Any]:
        """Returns analytics strictly scoped to the user's verified brand tenant."""
        self._assert_brand_ownership(user, brand_id)
        return self.brand_repo.get_brand_analytics(brand_id)

    def get_brand_products(self, user: User, brand_id: int) -> List[Dict[str, Any]]:
        """Returns product catalog strictly scoped to the user's brand tenant."""
        self._assert_brand_ownership(user, brand_id)
        products = self.brand_repo.get_brand_products(brand_id)
        results = []
        for p in products:
            skus_out = [
                {
                    "id": s.id,
                    "product_id": s.product_id,
                    "sku_code": s.sku_code,
                    "size": s.size,
                    "color": s.color,
                    "color_hex": s.color_hex,
                    "price_override": s.price_override,
                    "stock_level": s.stock_level,
                    "is_in_stock": s.is_in_stock
                }
                for s in p.skus
            ]
            results.append({
                "id": p.id,
                "brand_id": p.brand_id,
                "brand_name": p.brand.brand_name if p.brand else "CONFIT",
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else "Category",
                "title": p.title,
                "title_ar": p.title_ar,
                "slug": p.slug,
                "base_price": p.base_price,
                "currency": p.currency,
                "thumbnail_url": p.thumbnail_url,
                "color_family": p.color_family,
                "dominant_hex": p.dominant_hex,
                "style_tags": json.loads(p.style_tags) if p.style_tags else [],
                "occasion_tags": json.loads(p.occasion_tags) if p.occasion_tags else [],
                "rating": p.rating,
                "style_compatibility_score": None,
                "ai_fit_score": None,
                "is_featured": p.is_featured,
                "skus": skus_out
            })
        return results

    def update_sku(self, user: User, sku_id: int, stock_level: int, price_override: Optional[float] = None) -> Dict[str, Any]:
        """Updates SKU inventory and price with strict tenant ownership verification."""
        sku = self.db.query(ProductSKU).filter(ProductSKU.id == sku_id).first()
        if not sku:
            raise ResourceNotFoundError("ProductSKU", sku_id)

        product = self.db.query(Product).filter(Product.id == sku.product_id).first()
        if not product:
            raise ResourceNotFoundError("Product for SKU", sku_id)

        # Enforce Tenant Isolation: Only SKU owner or Platform Admin can mutate
        self._assert_brand_ownership(user, product.brand_id)

        updated_sku = self.brand_repo.update_sku_stock(sku_id, stock_level, price_override)
        return {
            "id": updated_sku.id,
            "product_id": updated_sku.product_id,
            "sku_code": updated_sku.sku_code,
            "size": updated_sku.size,
            "color": updated_sku.color,
            "color_hex": updated_sku.color_hex,
            "price_override": updated_sku.price_override,
            "stock_level": updated_sku.stock_level,
            "is_in_stock": updated_sku.is_in_stock
        }

    def create_sponsored_placement(self, user: User, brand_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates sponsored ad placement with tenant and product ownership verification."""
        self._assert_brand_ownership(user, brand_id)

        product = self.db.query(Product).filter(Product.id == data["product_id"]).first()
        if not product or product.brand_id != brand_id:
            raise ValidationDomainError(f"Product {data['product_id']} does not belong to your brand organization.")

        # Parse dates if provided. An unparseable date is a client error — it
        # used to be silently replaced by None (placement quietly became open-ended).
        from datetime import datetime

        def _parse_iso(value, field):
            if value is None or isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    raise ValidationDomainError(f"{field} must be an ISO-8601 datetime (got {value!r})")
            raise ValidationDomainError(f"{field} must be an ISO-8601 datetime string")

        start_date = _parse_iso(data.get("start_date"), "start_date")
        end_date = _parse_iso(data.get("end_date"), "end_date")

        try:
            p = self.brand_repo.create_placement(
                brand_id=brand_id,
                product_id=data["product_id"],
                placement_type=data.get("placement_type", "stylist_featured"),
                bid_amount=data.get("bid_amount_per_click", 0.50),
                daily_budget=data.get("daily_budget", 50.0),
                start_date=start_date,
                end_date=end_date
            )
        except ValueError as e:
            raise ValidationDomainError(str(e))
        return {
            "id": p.id,
            "brand_id": p.brand_id,
            "product_id": p.product_id,
            "product_title": p.product.title if p.product else "Product",
            "placement_type": p.placement_type,
            "bid_amount_per_click": p.bid_amount_per_click,
            "daily_budget": p.daily_budget,
            "spent_today": p.spent_today,
            "status": p.status,
            "impressions": p.impressions,
            "clicks": p.clicks,
            "conversions": p.conversions,
            "revenue_generated": p.revenue_generated,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "updated_at": p.updated_at,
            "created_at": p.created_at
        }

    def get_placements(self, user: User, brand_id: int) -> List[Dict[str, Any]]:
        """Returns sponsored placements strictly scoped to the verified brand tenant."""
        self._assert_brand_ownership(user, brand_id)
        placements = self.brand_repo.get_brand_placements(brand_id)
        return [
            {
                "id": p.id,
                "brand_id": p.brand_id,
                "product_id": p.product_id,
                "product_title": p.product.title if p.product else "Product",
                "placement_type": p.placement_type,
                "bid_amount_per_click": p.bid_amount_per_click,
                "daily_budget": p.daily_budget,
                "spent_today": p.spent_today,
                "status": p.status,
                "impressions": p.impressions,
                "clicks": p.clicks,
                "conversions": p.conversions,
                "revenue_generated": p.revenue_generated,
                "start_date": p.start_date,
            "end_date": p.end_date,
            "updated_at": p.updated_at,
            "created_at": p.created_at
            }
            for p in placements
        ]

    def assert_brand_ownership(self, user: User, target_brand_id: int) -> None:
        """Public alias: controllers that bypass a dashboard helper still need
        the tenant check, and must not reach for a private name to get it."""
        self._assert_brand_ownership(user, target_brand_id)

    def _assert_brand_ownership(self, user: User, target_brand_id: int) -> None:
        """Verifies that the user has tenant authorization for target_brand_id."""
        if user.role == UserRole.ADMIN:
            return  # Platform Admin has global oversight

        # Resolved through the memo rather than the user.brand_profile lazy
        # load: same row, same authorization decision, but it reuses the lookup
        # the request has already paid for. The check itself is unchanged --
        # a user still reaches exactly one brand, and a mismatch still raises.
        try:
            bp = self._resolve_brand(user)
        except AuthorizationError:
            raise AuthorizationError("Access denied: User is not linked to any Brand Organization.")

        if bp.id != target_brand_id:
            raise AuthorizationError(
                f"Tenant scope violation: Your account belongs to Brand #{bp.id} ({bp.brand_name}) "
                f"and cannot access or mutate resources of Brand #{target_brand_id}."
            )

    def _format_brand(self, bp: BrandProfile) -> Dict[str, Any]:
        return {
            "id": bp.id,
            "user_id": bp.user_id,
            "brand_name": bp.brand_name,
            "slug": bp.slug,
            "logo_url": bp.logo_url,
            "banner_url": bp.banner_url,
            "description": bp.description,
            "website": bp.website,
            "commission_rate": bp.commission_rate,
            "return_rate_benchmark": bp.return_rate_benchmark,
            "current_return_rate": bp.current_return_rate,
            "is_verified": bp.is_verified,
            "created_at": bp.created_at
        }

    def register_brand(
        self,
        *,
        brand_name: str,
        email: str,
        password: str,
        full_name: str,
        phone: Optional[str] = None,
        description: Optional[str] = None,
        description_ar: Optional[str] = None,
        website: Optional[str] = None,
        logo_url: Optional[str] = None,
        country: Optional[str] = "UAE",
        city: Optional[str] = "Dubai",
        preferred_language: str = "en",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        requesting_user: Optional[User] = None,
    ) -> Dict[str, Any]:
        """Automatically registers a brand owner and provisions their BrandProfile and workspace.

        Idempotent: if the brand or user already exists and matches credentials, resolves existing.
        """
        clean_name = brand_name.strip()
        if len(clean_name) < 2:
            raise ValidationDomainError("Brand name must be at least 2 characters.")

        clean_email = email.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean_email):
            raise ValidationDomainError("Please enter a valid work email address.")

        if len(password) < 8:
            raise ValidationDomainError("Password must be at least 8 characters.")

        # Check existing user
        user = requesting_user
        if user is None:
            user = self.db.query(User).filter(User.email == clean_email).first()
            if user:
                # Existing user: verify credentials
                if not verify_password(password, user.hashed_password):
                    raise ValidationDomainError("An account with this email already exists. Please verify your password.")
                # Upgrade role if needed
                if user.role == UserRole.CONSUMER:
                    user.role = UserRole.BRAND_OWNER
                    self.db.commit()
            else:
                # Create brand owner user
                user = User(
                    email=clean_email,
                    hashed_password=get_password_hash(password),
                    full_name=full_name.strip(),
                    role=UserRole.BRAND_OWNER,
                    phone=phone.strip() if phone else None,
                    preferred_language=preferred_language if preferred_language in ["en", "ar"] else "en",
                    is_active=True,
                    is_verified=False,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                self.db.add(user)
                self.db.commit()
                self.db.refresh(user)

        # Check if user already has a brand profile
        existing_profile = self.brand_repo.get_by_user_id(user.id)
        if existing_profile:
            # Idempotent response
            tokens = AuthService(self.db)._issue_session_tokens(user, ip_address, user_agent)
            return {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "token_type": "bearer",
                "brand": self._format_brand(existing_profile),
                "status": "existing",
                "next_step": "branches",
                "is_verified": existing_profile.is_verified,
                "message": "Welcome back! Your brand profile is already established on CONFIT_A.",
            }

        # Check for brand name duplicate across other tenants
        name_conflict = self.brand_repo.get_by_name(clean_name)
        if name_conflict and name_conflict.user_id != user.id:
            raise ValidationDomainError(f"A brand named '{clean_name}' is already registered on CONFIT_A.")

        # Generate unique slug
        base_slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-")
        if not base_slug:
            base_slug = "brand"
        candidate_slug = base_slug
        suffix = 2
        while True:
            existing_slug = self.brand_repo.get_by_slug(candidate_slug)
            if not existing_slug:
                break
            candidate_slug = f"{base_slug}-{suffix}"
            suffix += 1

        # Create BrandProfile (unverified by default — requires platform moderation/review)
        bp = self.brand_repo.create_brand_profile(
            user_id=user.id,
            brand_name=clean_name,
            slug=candidate_slug,
            description=description.strip() if description else None,
            description_ar=description_ar.strip() if description_ar else description,
            website=website.strip() if website else None,
            logo_url=logo_url.strip() if logo_url else None,
            is_verified=False,
        )

        # Issue tokens
        tokens = AuthService(self.db)._issue_session_tokens(user, ip_address, user_agent)

        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "brand": self._format_brand(bp),
            "status": "created",
            "next_step": "branches",
            "is_verified": bp.is_verified,
            "message": "Welcome to CONFIT_A! Your brand profile has been created successfully. You can now set up your stores, add products, and build your brand's presence on the platform.",
        }

    def get_onboarding_status(self, user: User) -> Dict[str, Any]:
        """Calculates granular 7-step onboarding progress and real verification status."""
        bp = self._resolve_brand(user)
        stores = self.brand_repo.get_brand_stores(bp.id)
        products = self.brand_repo.get_brand_products(bp.id)
        promos = self.db.query(SponsoredPlacement).filter(
            SponsoredPlacement.brand_id == bp.id,
            SponsoredPlacement.status == "active"
        ).all()
        inventory_rows_count = (
            self.db.query(StoreInventory)
            .join(StoreLocation, StoreLocation.id == StoreInventory.store_id)
            .filter(StoreLocation.brand_id == bp.id)
            .count()
        )

        step_profile = bool(bp.logo_url and bp.description and len(bp.description.strip()) >= 10)
        step_branches = len(stores) > 0
        step_locations = any(
            (s.latitude != 0.0 or s.longitude != 0.0) and -90 <= s.latitude <= 90 and -180 <= s.longitude <= 180
            for s in stores
        )
        step_products = len(products) > 0
        step_inventory = inventory_rows_count > 0
        step_promotions = len(promos) > 0
        step_published = bool(bp.is_verified)

        steps = [
            {
                "key": "profile",
                "title": "Complete Brand Profile",
                "description": "Upload high-resolution logo, official description, and contact details.",
                "is_completed": step_profile,
                "action_url": "/partner/profile",
            },
            {
                "key": "branches",
                "title": "Add Physical Boutique or Branch",
                "description": "Add store addresses, opening hours, contact numbers, and BOPIS instructions.",
                "is_completed": step_branches,
                "action_url": "/partner/branches",
            },
            {
                "key": "locations",
                "title": "Verify Branch Coordinates",
                "description": "Ensure accurate latitude/longitude coordinates for turn-by-turn Google Maps navigation.",
                "is_completed": step_locations,
                "action_url": "/partner/branches",
            },
            {
                "key": "products",
                "title": "Populate Clothing Catalog",
                "description": "Import products, sizes, prices, and high-fashion imagery.",
                "is_completed": step_products,
                "action_url": "/partner/catalog",
            },
            {
                "key": "inventory",
                "title": "Configure In-Store Stock Levels",
                "description": "Assign size-level SKU stock quantities across your boutique network.",
                "is_completed": step_inventory,
                "action_url": "/partner/inventory",
            },
            {
                "key": "promotions",
                "title": "Launch Brand Offers & Placements",
                "description": "Set up promotional discounts or sponsored stylist placements.",
                "is_completed": step_promotions,
                "action_url": "/partner/placements",
            },
            {
                "key": "verification",
                "title": "Platform Review & Publication",
                "description": "Admin verification verifies your brand house for customer discovery.",
                "is_completed": step_published,
                "action_url": f"/brands/{bp.slug}",
            },
        ]

        completed_count = sum(1 for s in steps if s["is_completed"])
        total_count = len(steps)
        percentage = int(round((completed_count / total_count) * 100))

        # Dynamic, honest messaging based on brand verification state
        if bp.is_verified:
            pub_status = "active"
            welcome_msg = (
                "Welcome back! Your brand is registered and visible to customers. "
                "Keep your store locations and product availability up to date."
            )
            cta_label = "Manage Branches & Stock"
            cta_url = "/partner/branches"
        elif completed_count >= 5:
            pub_status = "pending_review"
            welcome_msg = (
                "Your brand profile has been created and submitted for review. "
                "You can continue preparing your branch information and product catalog while approval is pending."
            )
            cta_label = "Preview Customer Experience"
            cta_url = f"/brands/{bp.slug}"
        else:
            pub_status = "draft"
            welcome_msg = (
                "Your brand profile is ready. Add your first branch and products to help customers discover your business."
            )
            first_incomplete = next((s for s in steps if not s["is_completed"]), steps[1])
            cta_label = "Complete Your Brand Setup"
            cta_url = first_incomplete["action_url"]

        return {
            "brand_id": bp.id,
            "brand_name": bp.brand_name,
            "is_verified": bp.is_verified,
            "is_published": bp.is_verified,
            "publication_status": pub_status,
            "welcome_message": welcome_msg,
            "primary_cta_label": cta_label,
            "primary_cta_url": cta_url,
            "completed_steps_count": completed_count,
            "total_steps_count": total_count,
            "completion_percentage": percentage,
            "steps": steps,
            "stores_count": len(stores),
            "products_count": len(products),
            "active_promotions_count": len(promos),
        }
