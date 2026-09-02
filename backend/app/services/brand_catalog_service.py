import csv
import io
import json
import hashlib
import re
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from decimal import Decimal
from backend.app.core.money import to_decimal, to_float, quantize_money
from backend.app.models.catalog import Product, ProductSKU, Category
from backend.app.models.user import BrandProfile
from backend.app.repositories.brand_repository import BrandRepository
from backend.app.core.logging import logger


class CatalogImportError:
    def __init__(self, row: int, field: str, message: str, value: Any = None):
        self.row = row
        self.field = field
        self.message = message
        self.value = value

    def to_dict(self):
        return {
            "row": self.row,
            "field": self.field,
            "message": self.message,
            "value": str(self.value)[:200] if self.value else None
        }


class BrandCatalogService:
    """
    Real CSV ingestion pipeline with:
    - Schema validation
    - Type validation
    - SKU uniqueness (DB constraint + upsert)
    - Idempotency
    - Transactional behavior
    - Partial failure reporting
    - CSV injection protection
    """

    REQUIRED_FIELDS = ["title", "category_slug", "base_price", "color_family", "thumbnail_url"]
    OPTIONAL_FIELDS = ["title_ar", "description", "description_ar", "material", "currency", "style_tags", "occasion_tags", "images", "sku_code", "size", "color", "stock_level", "price_override"]

    # Dangerous spreadsheet formula prefixes for CSV injection
    DANGEROUS_PREFIXES = ["=", "+", "-", "@", "\t", "\r"]

    def __init__(self, db: Session):
        self.db = db
        self.brand_repo = BrandRepository(db)

    def _sanitize_csv_value(self, value: str) -> str:
        """Prevent CSV injection by sanitizing formula prefixes"""
        if not isinstance(value, str):
            return value
        stripped = value.lstrip()
        for prefix in self.DANGEROUS_PREFIXES:
            if stripped.startswith(prefix):
                # Prefix with single quote to neutralize formula
                return "'" + value
        return value

    def _validate_row(self, row: Dict[str, Any], row_num: int) -> List[CatalogImportError]:
        errors = []

        # Required fields
        for field in self.REQUIRED_FIELDS:
            if field not in row or not row[field] or str(row[field]).strip() == "":
                errors.append(CatalogImportError(row_num, field, f"Missing required field: {field}", row.get(field)))

        # Type validation
        if "base_price" in row and row["base_price"]:
            try:
                price = to_decimal(row["base_price"])
                if price <= 0:
                    errors.append(CatalogImportError(row_num, "base_price", "Price must be positive", row["base_price"]))
                if price > 100000:
                    errors.append(CatalogImportError(row_num, "base_price", "Price exceeds maximum", row["base_price"]))
            except ValueError:
                errors.append(CatalogImportError(row_num, "base_price", "Invalid price format", row["base_price"]))

        if "stock_level" in row and row["stock_level"]:
            try:
                stock = int(row["stock_level"])
                if stock < 0:
                    errors.append(CatalogImportError(row_num, "stock_level", "Stock cannot be negative", row["stock_level"]))
            except ValueError:
                errors.append(CatalogImportError(row_num, "stock_level", "Invalid stock format", row["stock_level"]))

        # SKU validation
        if "sku_code" in row and row["sku_code"]:
            sku = str(row["sku_code"]).strip()
            if len(sku) < 3:
                errors.append(CatalogImportError(row_num, "sku_code", "SKU too short (min 3 chars)", sku))
            if len(sku) > 100:
                errors.append(CatalogImportError(row_num, "sku_code", "SKU too long (max 100 chars)", sku))
            if not re.match(r'^[A-Za-z0-9\-_]+$', sku):
                errors.append(CatalogImportError(row_num, "sku_code", "SKU contains invalid characters (only alphanumeric, -, _)", sku))

        # Category validation
        if "category_slug" in row and row["category_slug"]:
            slug = str(row["category_slug"]).strip()
            category = self.db.query(Category).filter(Category.slug == slug).first()
            if not category:
                errors.append(CatalogImportError(row_num, "category_slug", f"Category not found: {slug}", slug))

        # URL validation for thumbnail
        if "thumbnail_url" in row and row["thumbnail_url"]:
            url = str(row["thumbnail_url"]).strip()
            if not (url.startswith("http://") or url.startswith("https://") or url.startswith("data:image")):
                errors.append(CatalogImportError(row_num, "thumbnail_url", "Invalid URL format", url[:100]))

        return errors

    def _generate_sku_code(self, product_title: str, size: str, color: str, brand_slug: str) -> str:
        """Generate deterministic SKU code"""
        base = f"{brand_slug[:3].upper()}-{product_title[:3].upper()}-{size.upper()}-{color[:3].upper()}"
        # Add hash for uniqueness
        hash_part = hashlib.md5(f"{product_title}{size}{color}".encode()).hexdigest()[:4].upper()
        return f"{base}-{hash_part}"

    def parse_csv(self, csv_content: str, brand_id: int) -> Tuple[List[Dict[str, Any]], List[CatalogImportError], Dict[str, int]]:
        """
        Parse CSV with validation, returns (valid_rows, errors, stats)
        Stats: total, accepted, rejected, duplicate
        """
        errors: List[CatalogImportError] = []
        valid_rows: List[Dict[str, Any]] = []
        seen_skus = set()
        duplicate_count = 0

        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            # Validate headers
            if not reader.fieldnames:
                errors.append(CatalogImportError(0, "header", "CSV has no headers", None))
                return valid_rows, errors, {"total": 0, "accepted": 0, "rejected": 1, "duplicate": 0}

            # Check for required headers
            missing_headers = [f for f in self.REQUIRED_FIELDS if f not in reader.fieldnames]
            if missing_headers:
                errors.append(CatalogImportError(0, "header", f"Missing required headers: {missing_headers}", reader.fieldnames))
                return valid_rows, errors, {"total": 0, "accepted": 0, "rejected": 1, "duplicate": 0}

            for row_num, row in enumerate(reader, start=2):  # Start at 2 because header is row 1
                # Sanitize all string values for CSV injection
                sanitized_row = {}
                for k, v in row.items():
                    if isinstance(v, str):
                        sanitized_row[k] = self._sanitize_csv_value(v.strip())
                    else:
                        sanitized_row[k] = v

                # Validate row
                row_errors = self._validate_row(sanitized_row, row_num)
                if row_errors:
                    errors.extend(row_errors)
                    continue

                # Check duplicate SKU in file
                sku_code = sanitized_row.get("sku_code", "").strip()
                if sku_code:
                    if sku_code in seen_skus:
                        errors.append(CatalogImportError(row_num, "sku_code", f"Duplicate SKU in file: {sku_code}", sku_code))
                        duplicate_count += 1
                        continue
                    seen_skus.add(sku_code)

                    # Check duplicate in DB
                    existing = self.db.query(ProductSKU).filter(ProductSKU.sku_code == sku_code).first()
                    if existing:
                        # This is an upsert, not error - but count as duplicate for reporting
                        duplicate_count += 1

                valid_rows.append(sanitized_row)

        except csv.Error as e:
            errors.append(CatalogImportError(0, "csv", f"CSV parsing error: {str(e)}", None))

        total = len(valid_rows) + len([e for e in errors if e.row != 0])
        stats = {
            "total": total,
            "accepted": len(valid_rows),
            "rejected": len(errors),
            "duplicate": duplicate_count
        }

        return valid_rows, errors, stats

    def import_products(self, valid_rows: List[Dict[str, Any]], brand_id: int) -> Tuple[int, int, List[Dict[str, Any]]]:
        """
        Import valid rows with transactional behavior and upsert semantics.
        Returns (accepted, rejected, errors)
        """
        brand = self.db.query(BrandProfile).filter(BrandProfile.id == brand_id).first()
        if not brand:
            raise ValueError(f"Brand {brand_id} not found")

        accepted = 0
        rejected = 0
        import_errors = []

        for row_num, row in enumerate(valid_rows, start=2):
            try:
                # Get category
                category = self.db.query(Category).filter(Category.slug == row["category_slug"]).first()
                if not category:
                    import_errors.append({"row": row_num, "error": f"Category {row['category_slug']} not found"})
                    rejected += 1
                    continue

                # Check if product exists by title and brand (for upsert)
                existing_product = self.db.query(Product).filter(
                    Product.brand_id == brand_id,
                    Product.title == row["title"]
                ).first()

                if existing_product:
                    # Update existing product
                    product = existing_product
                    product.category_id = category.id
                    product.base_price = to_decimal(row["base_price"])
                    product.color_family = row["color_family"][:50]
                    product.thumbnail_url = row["thumbnail_url"][:1000]
                    if row.get("title_ar"):
                        product.title_ar = row["title_ar"][:255]
                    if row.get("description"):
                        product.description = row["description"][:2000]
                    if row.get("description_ar"):
                        product.description_ar = row["description_ar"][:2000]
                    if row.get("material"):
                        product.material = row["material"][:255]
                    if row.get("currency"):
                        product.currency = row["currency"][:10]
                    if row.get("style_tags"):
                        try:
                            tags = json.loads(row["style_tags"]) if isinstance(row["style_tags"], str) and row["style_tags"].startswith("[") else [t.strip() for t in row["style_tags"].split(",")]
                            product.style_tags = json.dumps(tags)
                        except:
                            product.style_tags = json.dumps([row["style_tags"]])
                else:
                    # Create new product
                    # Generate slug
                    slug_base = re.sub(r'[^a-z0-9]+', '-', row["title"].lower()).strip('-')
                    slug = f"{slug_base}-{brand_id}-{hashlib.md5(row['title'].encode()).hexdigest()[:6]}"
                    # Ensure unique slug
                    counter = 1
                    original_slug = slug
                    while self.db.query(Product).filter(Product.slug == slug).first():
                        slug = f"{original_slug}-{counter}"
                        counter += 1

                    product = Product(
                        brand_id=brand_id,
                        category_id=category.id,
                        title=row["title"][:255],
                        title_ar=row.get("title_ar", row["title"])[:255],
                        slug=slug[:255],
                        description=row.get("description", row["title"])[:2000],
                        description_ar=row.get("description_ar", row.get("description", row["title"]))[:2000],
                        base_price=to_decimal(row["base_price"]),
                        currency=row.get("currency", "USD")[:10],
                        material=row.get("material", "")[:255] if row.get("material") else None,
                        color_family=row["color_family"][:50],
                        dominant_hex=row.get("dominant_hex", "#1B1F3B")[:20],
                        thumbnail_url=row["thumbnail_url"][:1000],
                        images=row.get("images", "[]")[:5000],
                        style_tags=row.get("style_tags", "[]")[:2000],
                        occasion_tags=row.get("occasion_tags", "[]")[:2000],
                        is_active=True
                    )
                    self.db.add(product)
                    self.db.flush()  # Get product.id

                # Handle SKU
                sku_code = row.get("sku_code", "").strip()
                if not sku_code:
                    size = row.get("size", "M")
                    color = row.get("color", row["color_family"])
                    sku_code = self._generate_sku_code(row["title"], size, color, brand.slug)

                # Check existing SKU for upsert
                existing_sku = self.db.query(ProductSKU).filter(ProductSKU.sku_code == sku_code).first()

                if existing_sku:
                    # Verify SKU belongs to same brand
                    existing_product_for_sku = self.db.query(Product).filter(Product.id == existing_sku.product_id).first()
                    if existing_product_for_sku and existing_product_for_sku.brand_id != brand_id:
                        import_errors.append({"row": row_num, "error": f"SKU {sku_code} already exists for different brand"})
                        rejected += 1
                        continue

                    # Update SKU
                    existing_sku.product_id = product.id
                    existing_sku.size = row.get("size", existing_sku.size)[:20]
                    existing_sku.color = row.get("color", existing_sku.color)[:50]
                    if row.get("stock_level"):
                        existing_sku.stock_level = int(row["stock_level"])
                        existing_sku.is_in_stock = int(row["stock_level"]) > 0
                    if row.get("price_override"):
                        existing_sku.price_override = to_decimal(row["price_override"])
                else:
                    # Create SKU
                    sku = ProductSKU(
                        product_id=product.id,
                        sku_code=sku_code[:100],
                        size=row.get("size", "M")[:20],
                        color=row.get("color", row["color_family"])[:50],
                        color_hex=row.get("color_hex", "#1B1F3B")[:20],
                        price_override=to_decimal(row["price_override"]) if row.get("price_override") else None,
                        stock_level=int(row.get("stock_level", 20)),
                        is_in_stock=int(row.get("stock_level", 20)) > 0
                    )
                    self.db.add(sku)

                self.db.commit()
                accepted += 1

            except IntegrityError as e:
                self.db.rollback()
                import_errors.append({"row": row_num, "error": f"Database integrity error: {str(e)[:200]}"})
                rejected += 1
                logger.warn("catalog_import_integrity_error", row=row_num, error=str(e))
            except Exception as e:
                self.db.rollback()
                import_errors.append({"row": row_num, "error": f"Import error: {str(e)[:200]}"})
                rejected += 1
                logger.error("catalog_import_error", row=row_num, error=str(e))

        return accepted, rejected, import_errors

    def process_csv_import(self, csv_content: str, brand_id: int, file_name: str = None) -> Dict[str, Any]:
        """
        Full pipeline: parse -> validate -> import with job tracking
        """
        # Create job
        job = self.brand_repo.create_import_job(brand_id, file_name, len(csv_content))

        try:
            job.status = "processing"
            job.started_at = datetime.now(timezone.utc)
            self.db.commit()

            # Parse and validate
            valid_rows, validation_errors, stats = self.parse_csv(csv_content, brand_id)

            job.total_rows = stats["total"]
            job.duplicate_rows = stats["duplicate"]

            if not valid_rows and validation_errors:
                job.status = "failed"
                job.rejected_rows = stats["rejected"]
                job.errors_json = json.dumps([e.to_dict() for e in validation_errors])
                job.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                return {
                    "job_id": job.id,
                    "status": job.status,
                    "total_rows": job.total_rows,
                    "accepted_rows": 0,
                    "rejected_rows": job.rejected_rows,
                    "duplicate_rows": job.duplicate_rows,
                    "errors": [e.to_dict() for e in validation_errors]
                }

            # Import
            accepted, rejected, import_errors = self.import_products(valid_rows, brand_id)

            # Combine errors
            all_errors = [e.to_dict() for e in validation_errors] + import_errors

            job.accepted_rows = accepted
            job.rejected_rows = len(all_errors)
            job.errors_json = json.dumps(all_errors)

            if accepted > 0 and len(all_errors) == 0:
                job.status = "completed"
            elif accepted > 0 and len(all_errors) > 0:
                job.status = "partially_completed"
            else:
                job.status = "failed"

            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            return {
                "job_id": job.id,
                "status": job.status,
                "total_rows": job.total_rows,
                "accepted_rows": job.accepted_rows,
                "rejected_rows": job.rejected_rows,
                "duplicate_rows": job.duplicate_rows,
                "errors": all_errors
            }

        except Exception as e:
            job.status = "failed"
            job.errors_json = json.dumps([{"row": 0, "field": "system", "message": str(e)[:500]}])
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            logger.error("catalog_import_job_failed", job_id=job.id, error=str(e))
            raise
