from backend.app.services.partner_audit import append_event
"""Bounded CSV/JSON ingestion with shared validation and row-atomic upserts.

Identity is (brand, title) for products, globally unique sku_code for variants.
An import may update a variant, but cannot move it to a different product.
Partial success is intentional: each accepted row commits independently.
"""
import csv
import io
import json
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Any, Dict, List, Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.core.money import validate_money
from backend.app.core.logging import logger
from backend.app.models.catalog import Product, ProductSKU, Category
from backend.app.models.user import BrandProfile, AuditLog
from backend.app.repositories.brand_repository import BrandRepository


class CatalogImportError:
    def __init__(self, row, field, message, value=None):
        self.row, self.field, self.message, self.value = row, field, message, value

    def to_dict(self):
        return dict(row=self.row, field=self.field, message=self.message,
                    value=str(self.value)[:200] if self.value is not None else None)


class BrandCatalogService:
    MAX_ROWS = 1000
    MAX_BYTES = 10 * 1024 * 1024
    REQUIRED_FIELDS = ['title', 'category_slug', 'base_price', 'color_family']
    OPTIONAL_FIELDS = ['title_ar', 'description', 'description_ar', 'material', 'currency',
                       'style_tags', 'occasion_tags', 'images', 'sku_code', 'size', 'color',
                       'stock_level', 'price_override', 'dominant_hex', 'color_hex']
    DANGEROUS_PREFIXES = ['=', '+', '-', '@', '\t', '\r']
    LIMITS = dict(title=255, title_ar=255, description=2000, description_ar=2000,
                  material=255, color_family=50, thumbnail_url=1000, size=20, color=50,
                  sku_code=100, category_slug=100)

    def __init__(self, db: Session):
        self.db = db
        self.brand_repo = BrandRepository(db)

    def _sanitize_csv_value(self, value):
        # Defence for text that may later be opened by a spreadsheet. Numeric
        # columns are validated as numbers, NOT prefixed/changed into strings.
        if isinstance(value, str) and value.lstrip().startswith(tuple(self.DANGEROUS_PREFIXES)):
            return "'" + value
        return value

    def _normalize(self, source):
        row = {k: v.strip() if isinstance(v, str) else v for k, v in source.items()}
        for field, default in dict(size='M', stock_level='0', currency='USD',
                                   color=row.get('color_family', ''), sku_code='').items():
            if row.get(field) in (None, ''):
                row[field] = default
        return row

    def _validate_row(self, row: Dict[str, Any], row_num: int) -> List[CatalogImportError]:
        errors = []
        def error(field, message):
            errors.append(CatalogImportError(row_num, field, message, row.get(field)))
        for field in self.REQUIRED_FIELDS:
            if row.get(field) is None or str(row[field]).strip() == '':
                error(field, f'Missing required field: {field}')
        for field, limit in self.LIMITS.items():
            value = row.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                error(field, f'Must be text of at most {limit} characters')
        for field in ('base_price', 'price_override'):
            if row.get(field) not in (None, ''):
                try:
                    value = validate_money(row[field], field, allow_zero=False, required=True, exact_scale=True)
                    if value > BrandRepository.MAX_SKU_PRICE:
                        error(field, 'Price exceeds maximum')
                except (ValueError, TypeError):
                    error(field, 'Price must be finite, positive and have at most two decimal places')
        value = row.get('stock_level', 0)
        if isinstance(value, bool) or not re.fullmatch(r'\d{1,6}', str(value)) or not 0 <= int(value) <= 100000:
            error('stock_level', 'Stock must be a whole number between 0 and 100000')
        sku = row.get('sku_code')
        if sku and (not isinstance(sku, str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,100}', sku)):
            error('sku_code', 'SKU must contain 3–100 letters, digits, hyphens or underscores')
        slug = row.get('category_slug')
        if isinstance(slug, str) and slug and not self.db.query(Category.id).filter(Category.slug == slug).first():
            error('category_slug', 'Category not found')
        url = row.get('thumbnail_url')
        if isinstance(url, str) and url:
            try:
                parsed = urlsplit(url)
                if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError()
            except ValueError:
                error('thumbnail_url', 'A public HTTP(S) image URL without credentials is required')
        if not isinstance(row.get('currency'), str) or not re.fullmatch(r'[A-Z]{3}', row['currency']):
            error('currency', 'Use a three-letter uppercase currency code')
        for field in ('style_tags', 'occasion_tags', 'images'):
            value = row.get(field)
            if value in (None, ''):
                row[field] = '[]'
                continue
            try:
                if isinstance(value, str):
                    value = json.loads(value) if value.startswith('[') else value.split(',')
                if not isinstance(value, list) or len(value) > 100 or any(not isinstance(v, str) or len(v) > 1000 for v in value):
                    raise ValueError()
                encoded = json.dumps(value, ensure_ascii=False)
                if len(encoded) > 5000:
                    raise ValueError()
                row[field] = encoded
            except (ValueError, TypeError):
                error(field, 'Must be a bounded array of strings or comma-separated text')
        for field in ('dominant_hex', 'color_hex'):
            if row.get(field) and (not isinstance(row[field], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', row[field])):
                error(field, 'Must be a six-digit hex color')
        return errors

    def _generate_sku_code(self, product_title, size, color, brand_slug):
        identity = json.dumps([brand_slug, product_title, size, color], ensure_ascii=False)
        return 'SKU-' + hashlib.sha256(identity.encode()).hexdigest()[:32].upper()

    def _prepare_rows(self, rows, brand_id):
        valid, errors, seen, duplicate = [], [], set(), 0
        brand = self.brand_repo.get_by_id(brand_id)
        if not brand:
            raise ValueError('Brand not found')
        for number, source in enumerate(rows, 2):
            if not isinstance(source, dict) or None in source:
                errors.append(CatalogImportError(number, 'row', 'Row has invalid structure or extra columns'))
                continue
            row = self._normalize(source)
            row_errors = self._validate_row(row, number)
            if row_errors:
                errors.extend(row_errors)
                continue
            row['_generated_sku'] = not bool(row.get('sku_code'))
            code = row.get('sku_code') or self._generate_sku_code(row['title'], row['size'], row['color'], brand.slug)
            if code in seen:
                errors.append(CatalogImportError(number, 'sku_code', 'Duplicate SKU in file', code))
                duplicate += 1
                continue
            seen.add(code)
            row['sku_code'], row['_row_number'] = code, number
            valid.append(row)
        return valid, errors, dict(total=len(rows), accepted=len(valid),
                                  rejected=len({e.row for e in errors}), duplicate=duplicate)

    def parse_csv(self, csv_content, brand_id) -> Tuple[list, list, dict]:
        try:
            reader = csv.DictReader(io.StringIO(csv_content.lstrip('\ufeff')), strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or any(f not in fields for f in self.REQUIRED_FIELDS):
                raise ValueError('CSV needs unique headers including: ' + ', '.join(self.REQUIRED_FIELDS))
            rows = []
            for source in reader:
                if len(rows) >= self.MAX_ROWS:
                    raise ValueError(f'At most {self.MAX_ROWS} rows per import')
                # Do not mutate numeric input before validation.
                rows.append({k: self._sanitize_csv_value(v) if k in ('title', 'title_ar', 'description', 'description_ar') else v for k,v in source.items()})
            if not rows:
                raise ValueError('CSV contains no data rows')
            return self._prepare_rows(rows, brand_id)
        except (csv.Error, ValueError) as exc:
            return [], [CatalogImportError(0, 'header' if 'header' in str(exc) else 'file', str(exc))], dict(total=0, accepted=0, rejected=0, duplicate=0)

    def import_products(self, valid_rows, brand_id, *, commit_each=True):
        accepted, rejected, errors = 0, 0, []
        for fallback_number, row in enumerate(valid_rows, 2):
            number = row.get('_row_number', fallback_number)
            try:
                # Lock a real parent row: locking a missing product/SKU cannot
                # serialize concurrent first imports. Reacquire after each commit.
                brand = self.db.query(BrandProfile).filter_by(id=brand_id).with_for_update().first()
                if not brand:
                    raise ValueError('Brand not found')
                category = self.db.query(Category).filter_by(slug=row['category_slug']).first()
                if not category:
                    raise ValueError('Category not found')
                code = row.get('sku_code') or self._generate_sku_code(row['title'], row.get('size','M'), row.get('color',row['color_family']), brand.slug)
                sku = self.db.query(ProductSKU).filter_by(sku_code=code).with_for_update().first()
                product = self.db.query(Product).filter_by(brand_id=brand_id, title=row['title']).first()
                if not sku and product and row.get('_generated_sku'):
                    # Preserve pre-existing generated codes during upgrades:
                    # a new generator must not create a second physical variant.
                    matches = self.db.query(ProductSKU).filter_by(product_id=product.id,
                        size=row['size'], color=row['color']).with_for_update().all()
                    if len(matches) > 1:
                        raise ValueError('Ambiguous variant: provide an explicit sku_code')
                    sku = matches[0] if matches else None
                if product and product.archived_at:
                    raise ValueError('Restore archived product to draft before import')
                if sku and (not product or sku.product_id != product.id):
                    raise ValueError('SKU already assigned to another product; reassignment is not allowed')
                if not product:
                    slug = 'brand-' + str(brand_id) + '-' + hashlib.sha256(row['title'].encode()).hexdigest()[:24]
                    product = Product(brand_id=brand_id, category_id=category.id, title=row['title'], slug=slug,
                                      title_ar=row.get('title_ar') or row['title'], description=row.get('description') or row['title'],
                                      description_ar=row.get('description_ar') or row.get('description') or row['title'],
                                      rating=0, review_count=0, style_compatibility_base=0, thumbnail_url=row.get('thumbnail_url') or '', is_active=bool(row.get('thumbnail_url')) and not brand.is_test)
                    self.db.add(product)
                product.category_id = category.id
                product.base_price = validate_money(row['base_price'], 'base_price', allow_zero=False, required=True, exact_scale=True)
                for field in ('color_family', 'thumbnail_url', 'currency', 'material', 'dominant_hex', 'title_ar', 'description', 'description_ar', 'style_tags', 'occasion_tags', 'images'):
                    if row.get(field) not in (None, ''):
                        setattr(product, field, row[field])
                self.db.flush()
                if not sku:
                    sku = ProductSKU(product_id=product.id, sku_code=code)
                    self.db.add(sku)
                sku.size = row.get('size') or 'M'
                sku.color = row.get('color') or row['color_family']
                sku.stock_level = int(row.get('stock_level') or 0)
                sku.is_in_stock = sku.stock_level > 0
                if row.get('price_override') not in (None, ''):
                    sku.price_override = validate_money(row['price_override'], 'price_override', allow_zero=False, required=True, exact_scale=True)
                if row.get('color_hex'):
                    sku.color_hex = row['color_hex']
                self.db.flush()
                append_event(self.db, brand_id, 'BRAND_CATALOG_ROW_IMPORTED', 'ProductSKU', sku.id,
                             after={'product_id': product.id, 'stock_level': sku.stock_level, 'row': number})
                if commit_each:
                    self.db.commit()
                accepted += 1
            except (ValueError, IntegrityError) as exc:
                if not commit_each:
                    raise
                self.db.rollback()  # includes product changes/flushes in a rejected row
                message = str(exc) if isinstance(exc, ValueError) else 'Catalog conflict; verify SKU uniqueness and retry'
                errors.append(CatalogImportError(number, 'row', message).to_dict())
                rejected += 1
            except Exception:
                if not commit_each:
                    raise
                self.db.rollback()
                logger.error('catalog_import_row_failed', row=number)
                raise  # infrastructure failures are not disguised as invalid input
        return accepted, rejected, errors

    def _process(self, brand_id, file_name, file_size, prepare, actor_id=None):
        self.db.info['partner_actor'] = actor_id
        job = self.brand_repo.create_import_job(brand_id, file_name, file_size)
        job_id = job.id
        try:
            job.status, job.started_at = 'processing', datetime.now(timezone.utc)
            self.db.commit()
            valid, validation_errors, stats = prepare()
            accepted, rejected, import_errors = self.import_products(valid, brand_id)
            errors = [e.to_dict() for e in validation_errors] + import_errors
            job.total_rows, job.accepted_rows = stats['total'], accepted
            job.rejected_rows = stats['rejected'] + rejected
            job.duplicate_rows = stats['duplicate']
            job.status = 'completed' if accepted and not errors else 'partially_completed' if accepted else 'failed'
            job.errors_json, job.completed_at = json.dumps(errors), datetime.now(timezone.utc)
            self.db.add(AuditLog(user_id=actor_id, action='BRAND_CATALOG_IMPORTED', resource_type='CatalogImportJob',
                                 resource_id=str(job_id), details_json=json.dumps(dict(brand_id=brand_id, accepted=accepted, rejected=job.rejected_rows))))
            self.db.commit()
            return dict(job_id=job.id, status=job.status, total_rows=job.total_rows, accepted_rows=job.accepted_rows,
                        rejected_rows=job.rejected_rows, duplicate_rows=job.duplicate_rows, errors=errors[:50])
        except Exception:
            self.db.rollback()
            job = self.brand_repo.get_import_job(job_id, brand_id)
            job.status, job.completed_at = 'failed', datetime.now(timezone.utc)
            job.errors_json = json.dumps([CatalogImportError(0, 'system', 'Import interrupted; inspect catalog before retrying').to_dict()])
            self.db.commit()
            raise

    def process_csv_import(self, csv_content, brand_id, file_name=None, actor_id=None):
        return self._process(brand_id, file_name, len(csv_content.encode()), lambda: self.parse_csv(csv_content, brand_id), actor_id)

    def process_json_import(self, products, brand_id, actor_id=None):
        return self._process(brand_id, 'api_import.json', None, lambda: self._prepare_rows(products, brand_id), actor_id)
