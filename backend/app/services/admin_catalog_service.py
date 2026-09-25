"""Explicit cross-brand catalog application service for platform admins.

The administrator never impersonates a brand and never receives a synthetic
BrandProfile. Every call carries an explicit brand id, every query repeats that
tenant predicate, and controllers pair mutations with a privileged audit event
in the same transaction.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError
from backend.app.models.brand_analytics import SponsoredPlacement
from backend.app.models.catalog import Category, Product, ProductSKU
from backend.app.models.user import BrandProfile
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.schemas.admin_catalog import (
    AdminCatalogProductCreate,
    AdminCatalogProductPatch,
    AdminCatalogSKUCreate,
    AdminCatalogSKUPatch,
)


class AdminCatalogService:
    """Database-backed admin catalog operations with no partner-session coupling."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = BrandRepository(db)

    def _brand(self, brand_id: int, *, lock: bool = False) -> BrandProfile:
        query = self.db.query(BrandProfile).filter(BrandProfile.id == brand_id)
        if lock:
            query = query.with_for_update()
        brand = query.first()
        if not brand:
            raise ResourceNotFoundError("BrandProfile", brand_id)
        return brand

    @staticmethod
    def _json_list(raw: str | None, field: str, product_id: int) -> List[str]:
        try:
            value = json.loads(raw or "[]")
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError(
                f"Stored {field} is invalid for product {product_id}", {field: "invalid JSON"}
            ) from exc
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValidationDomainError(
                f"Stored {field} is invalid for product {product_id}", {field: "expected list of text"}
            )
        return value

    def _serialize_product(self, product: Product) -> Dict[str, Any]:
        return {
            "id": product.id,
            "brand_id": product.brand_id,
            "brand_name": product.brand.brand_name,
            "category_id": product.category_id,
            "category_name": product.category.name,
            "category_slug": product.category.slug,
            "title": product.title,
            "title_ar": product.title_ar,
            "slug": product.slug,
            "description": product.description,
            "description_ar": product.description_ar,
            "base_price": float(product.base_price),
            "currency": product.currency,
            "material": product.material,
            "care_instructions": product.care_instructions,
            "color_family": product.color_family,
            "dominant_hex": product.dominant_hex,
            "thumbnail_url": product.thumbnail_url,
            "images": self._json_list(product.images, "images", product.id),
            "style_tags": self._json_list(product.style_tags, "style_tags", product.id),
            "occasion_tags": self._json_list(product.occasion_tags, "occasion_tags", product.id),
            "is_featured": bool(product.is_featured),
            "is_active": bool(product.is_active),
            "created_at": product.created_at,
            "skus": [
                {
                    "id": sku.id,
                    "product_id": sku.product_id,
                    "sku_code": sku.sku_code,
                    "size": sku.size,
                    "color": sku.color,
                    "color_hex": sku.color_hex,
                    "price_override": float(sku.price_override) if sku.price_override is not None else None,
                    "stock_level": int(sku.stock_level or 0),
                    "is_in_stock": bool(sku.is_in_stock),
                }
                for sku in sorted(product.skus, key=lambda row: (row.sku_code, row.id))
            ],
        }

    def _products(self, brand_id: int) -> List[Product]:
        return (
            self.db.query(Product)
            .options(joinedload(Product.brand), joinedload(Product.category), joinedload(Product.skus))
            .filter(Product.brand_id == brand_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
            .all()
        )

    def list_brands(self) -> List[Dict[str, Any]]:
        product_count = select(func.count(Product.id)).where(
            Product.brand_id == BrandProfile.id
        ).correlate(BrandProfile).scalar_subquery()
        active_count = select(func.count(Product.id)).where(
            Product.brand_id == BrandProfile.id, Product.is_active.is_(True)
        ).correlate(BrandProfile).scalar_subquery()
        sku_count = select(func.count(ProductSKU.id)).join(
            Product, Product.id == ProductSKU.product_id
        ).where(Product.brand_id == BrandProfile.id).correlate(BrandProfile).scalar_subquery()

        # Keep these imports local to make the count ownership obvious.
        from backend.app.models.catalog import StoreLocation
        store_count = select(func.count(StoreLocation.id)).where(
            StoreLocation.brand_id == BrandProfile.id
        ).correlate(BrandProfile).scalar_subquery()
        placement_count = select(func.count(SponsoredPlacement.id)).where(
            SponsoredPlacement.brand_id == BrandProfile.id
        ).correlate(BrandProfile).scalar_subquery()

        rows = self.db.execute(
            select(
                BrandProfile,
                product_count.label("product_count"),
                active_count.label("active_product_count"),
                sku_count.label("sku_count"),
                store_count.label("store_count"),
                placement_count.label("placement_count"),
            ).order_by(BrandProfile.brand_name.asc(), BrandProfile.id.asc())
        ).all()
        return [
            {
                "id": brand.id,
                "brand_name": brand.brand_name,
                "slug": brand.slug,
                "is_verified": bool(brand.is_verified),
                "product_count": int(total or 0),
                "active_product_count": int(active or 0),
                "sku_count": int(skus or 0),
                "store_count": int(stores or 0),
                "placement_count": int(placements or 0),
            }
            for brand, total, active, skus, stores, placements in rows
        ]

    def snapshot(self, brand_id: int) -> Dict[str, Any]:
        self._brand(brand_id)
        summaries = {row["id"]: row for row in self.list_brands()}
        products = self._products(brand_id)
        inventory_map = self.repo.get_brand_store_inventory_map(brand_id)
        product_rows = [self._serialize_product(product) for product in products]

        inventory = []
        for product, serialized in zip(products, product_rows):
            variants = []
            for sku, sku_out in zip(
                sorted(product.skus, key=lambda row: (row.sku_code, row.id)),
                serialized["skus"],
            ):
                stores = inventory_map.get(sku.id, [])
                variants.append({
                    **sku_out,
                    "store_inventories": [
                        {
                            "id": row.id,
                            "store_id": row.store_id,
                            "store_name": row.store_name,
                            "quantity": row.quantity,
                            "reserved": row.reserved_quantity,
                            "available": row.quantity - row.reserved_quantity,
                        }
                        for row in stores
                    ],
                })
            inventory.append({
                "product_id": product.id,
                "title": product.title,
                "thumbnail_url": product.thumbnail_url,
                "is_active": bool(product.is_active),
                "total_stock": sum(int(sku.stock_level or 0) for sku in product.skus),
                "skus": variants,
            })

        placements = [
            {
                "id": row.id,
                "brand_id": row.brand_id,
                "product_id": row.product_id,
                "product_title": row.product.title,
                "placement_type": row.placement_type,
                "bid_amount_per_click": float(row.bid_amount_per_click),
                "daily_budget": float(row.daily_budget),
                "spent_today": float(row.spent_today),
                "status": row.status,
                "impressions": row.impressions,
                "clicks": row.clicks,
                "conversions": row.conversions,
                "revenue_generated": float(row.revenue_generated),
                "start_date": row.start_date,
                "end_date": row.end_date,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in self.repo.get_brand_placements(brand_id)
        ]
        stores = [
            {
                "id": row.id,
                "name": row.name,
                "name_ar": row.name_ar,
                "city": row.city,
                "country": row.country,
                "address": row.address,
                "is_bopis_enabled": bool(row.is_bopis_enabled),
            }
            for row in self.repo.get_brand_stores(brand_id)
        ]
        imports = [
            {
                "job_id": row.id,
                "file_name": row.file_name,
                "status": row.status,
                "total_rows": row.total_rows,
                "accepted_rows": row.accepted_rows,
                "rejected_rows": row.rejected_rows,
                "duplicate_rows": row.duplicate_rows,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in self.repo.get_brand_import_jobs(brand_id, limit=50)
        ]
        categories = [
            {"id": row.id, "name": row.name, "name_ar": row.name_ar, "slug": row.slug}
            for row in self.db.query(Category).order_by(Category.name.asc()).all()
        ]
        return {
            "brand": summaries[brand_id],
            "products": product_rows,
            "inventory": inventory,
            "placements": placements,
            "stores": stores,
            "imports": imports,
            "categories": categories,
            "generated_at": datetime.now(timezone.utc),
        }

    def _category(self, category_id: int) -> Category:
        category = self.db.get(Category, category_id)
        if not category:
            raise ResourceNotFoundError("Category", category_id)
        return category

    def _assert_unique_title(self, brand_id: int, title: str, exclude_id: int | None = None) -> None:
        query = self.db.query(Product.id).filter(
            Product.brand_id == brand_id,
            func.lower(Product.title) == title.lower(),
        )
        if exclude_id is not None:
            query = query.filter(Product.id != exclude_id)
        if query.first():
            raise ValidationDomainError(
                "A product with this title already exists for the selected brand",
                {"title": "must be unique within the brand"},
            )

    def _assert_unique_skus(self, skus: List[AdminCatalogSKUCreate]) -> None:
        codes = [sku.sku_code for sku in skus]
        if len(set(codes)) != len(codes):
            raise ValidationDomainError("SKU codes must be unique", {"skus": "duplicate code in request"})
        existing = self.db.query(ProductSKU.sku_code).filter(ProductSKU.sku_code.in_(codes)).first()
        if existing:
            raise ValidationDomainError(
                "SKU code is already in use", {"sku_code": existing[0]}
            )

    def create_product(self, brand_id: int, payload: AdminCatalogProductCreate) -> Product:
        brand = self._brand(brand_id, lock=True)
        self._category(payload.category_id)
        self._assert_unique_title(brand_id, payload.title)
        self._assert_unique_skus(payload.skus)

        slug_hash = hashlib.sha256(f"{brand_id}:{payload.title}".encode("utf-8")).hexdigest()[:24]
        product = Product(
            brand_id=brand_id,
            category_id=payload.category_id,
            title=payload.title,
            title_ar=payload.title_ar,
            slug=f"brand-{brand_id}-{slug_hash}",
            description=payload.description,
            description_ar=payload.description_ar,
            base_price=payload.base_price,
            currency=payload.currency,
            material=payload.material,
            care_instructions=payload.care_instructions,
            color_family=payload.color_family,
            dominant_hex=payload.dominant_hex,
            thumbnail_url=str(payload.thumbnail_url),
            images=json.dumps([str(url) for url in payload.images], ensure_ascii=False),
            style_tags=json.dumps(payload.style_tags, ensure_ascii=False),
            occasion_tags=json.dumps(payload.occasion_tags, ensure_ascii=False),
            is_featured=payload.is_featured,
            is_active=True,
            rating=0,
            review_count=0,
            style_compatibility_base=0,
        )
        self.db.add(product)
        self.db.flush()
        for item in payload.skus:
            self.db.add(ProductSKU(
                product_id=product.id,
                sku_code=item.sku_code,
                size=item.size,
                color=item.color,
                color_hex=item.color_hex,
                price_override=item.price_override,
                stock_level=item.stock_level,
                is_in_stock=item.stock_level > 0,
            ))
        self.db.flush()
        return product

    def update_product(
        self, brand_id: int, product_id: int, payload: AdminCatalogProductPatch
    ) -> Product:
        self._brand(brand_id, lock=True)
        product = self.db.query(Product).filter(
            Product.id == product_id, Product.brand_id == brand_id
        ).with_for_update().first()
        if not product:
            raise ResourceNotFoundError("Product", product_id)
        changes = payload.model_dump(exclude_unset=True)
        if "category_id" in changes:
            self._category(changes["category_id"])
        if "title" in changes:
            self._assert_unique_title(brand_id, changes["title"], exclude_id=product_id)
        for field, value in changes.items():
            if field in {"images", "style_tags", "occasion_tags"}:
                value = json.dumps([str(item) for item in value], ensure_ascii=False)
            elif field == "thumbnail_url":
                value = str(value)
            setattr(product, field, value)
        self.db.flush()
        return product

    def add_sku(self, brand_id: int, product_id: int, payload: AdminCatalogSKUCreate) -> ProductSKU:
        self._brand(brand_id, lock=True)
        product = self.db.query(Product).filter(
            Product.id == product_id, Product.brand_id == brand_id
        ).with_for_update().first()
        if not product:
            raise ResourceNotFoundError("Product", product_id)
        self._assert_unique_skus([payload])
        sku = ProductSKU(
            product_id=product_id,
            sku_code=payload.sku_code,
            size=payload.size,
            color=payload.color,
            color_hex=payload.color_hex,
            price_override=payload.price_override,
            stock_level=payload.stock_level,
            is_in_stock=payload.stock_level > 0,
        )
        self.db.add(sku)
        self.db.flush()
        return sku

    def update_sku(
        self, brand_id: int, sku_id: int, payload: AdminCatalogSKUPatch
    ) -> ProductSKU:
        self._brand(brand_id, lock=True)
        sku = self.db.query(ProductSKU).join(Product).filter(
            ProductSKU.id == sku_id, Product.brand_id == brand_id
        ).with_for_update().first()
        if not sku:
            raise ResourceNotFoundError("ProductSKU", sku_id)
        changes = payload.model_dump(exclude_unset=True)
        if "stock_level" in changes:
            sku.stock_level = changes["stock_level"]
            sku.is_in_stock = changes["stock_level"] > 0
        if "price_override" in changes:
            sku.price_override = changes["price_override"]
        self.db.flush()
        return sku

    def set_product_active(self, brand_id: int, product_id: int, active: bool) -> tuple[Product, int]:
        self._brand(brand_id, lock=True)
        product = self.db.query(Product).filter(
            Product.id == product_id, Product.brand_id == brand_id
        ).with_for_update().first()
        if not product:
            raise ResourceNotFoundError("Product", product_id)
        product.is_active = active
        cancelled = 0
        if not active:
            placements = self.db.query(SponsoredPlacement).filter(
                SponsoredPlacement.brand_id == brand_id,
                SponsoredPlacement.product_id == product_id,
                SponsoredPlacement.status.in_(("active", "paused", "budget_exhausted")),
            ).with_for_update().all()
            for placement in placements:
                placement.status = "cancelled"
            cancelled = len(placements)
        self.db.flush()
        return product, cancelled
