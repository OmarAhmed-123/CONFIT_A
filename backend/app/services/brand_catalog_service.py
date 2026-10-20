"""Bounded CSV/JSON ingestion with shared validation and row-atomic upserts.

Identity is (brand, title) for products, globally unique sku_code for variants.
An import may update a variant, but cannot move it to a different product.
Partial success is intentional: each accepted row commits independently.
"""
import csv
import difflib
import io
import json
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.core.money import validate_money
from backend.app.core.logging import logger
from backend.app.models.catalog import Product, ProductSKU, Category, StoreLocation, StoreInventory
from backend.app.models.user import BrandProfile, AuditLog
from backend.app.repositories.brand_repository import BrandRepository


class CatalogHeaderError(ValueError):
    """Raised when the header row itself is unusable.

    Carrying the classification in the TYPE rather than sniffing for the word
    'header' inside the message means the wording can be improved freely
    without silently re-labelling the error's field as 'file'.
    """


class CatalogImportError:
    def __init__(self, row, field, message, value=None, suggestion=None):
        self.row, self.field, self.message, self.value, self.suggestion = row, field, message, value, suggestion

    def to_dict(self):
        res = dict(row=self.row, field=self.field, message=self.message,
                   value=str(self.value)[:200] if self.value is not None else None)
        if self.suggestion:
            res["suggestion"] = self.suggestion
        return res


class BrandCatalogService:
    MAX_ROWS = 1000
    MAX_BYTES = 10 * 1024 * 1024
    REQUIRED_FIELDS = ['title', 'category_slug', 'base_price', 'color_family', 'thumbnail_url']
    #: The category slugs the seeded catalogue actually creates
    #: (``backend/app/seed_data.py``). The CSV template and the validation hint
    #: used to name ``shirts``/``trousers``/``knitwear``, which do not exist, so
    #: two of the template's own four sample rows failed validation and a user
    #: who followed the hint was led straight back into the error.
    SEEDED_CATEGORY_SLUGS = ('outerwear', 'tops', 'bottoms', 'dresses', 'footwear', 'accessories')
    OPTIONAL_FIELDS = ['title_ar', 'description', 'description_ar', 'material', 'currency',
                       'style_tags', 'occasion_tags', 'images', 'sku_code', 'size', 'color',
                       'stock_level', 'price_override', 'dominant_hex', 'color_hex',
                       'store_id', 'branch_id', 'store_name', 'branch_name']
    DANGEROUS_PREFIXES = ['=', '+', '-', '@', '\t', '\r']
    LIMITS = dict(title=255, title_ar=255, description=2000, description_ar=2000,
                  material=255, color_family=50, thumbnail_url=1000, size=20, color=50,
                  sku_code=100, category_slug=100)

    HEADER_ALIASES = {
        'product_name': 'title',
        'product_title': 'title',
        'name': 'title',
        'category': 'category_slug',
        'price': 'base_price',
        'selling_price': 'base_price',
        'original_price': 'compare_at_price',
        'image_url': 'thumbnail_url',
        'image': 'thumbnail_url',
        'sku': 'sku_code',
        'stock_quantity': 'stock_level',
        'stock': 'stock_level',
        'quantity': 'stock_level',
        'branch_id': 'branch_id',
        'branch_name': 'branch_name',
        'branch_slug': 'branch_slug',
        'store_id': 'store_id',
        'store_name': 'store_name',
    }

    def __init__(self, db: Session):
        self.db = db
        self.brand_repo = BrandRepository(db)

    def _sanitize_csv_value(self, value):
        # Defence for text that may later be opened by a spreadsheet. Numeric
        # columns are validated as numbers, NOT prefixed/changed into strings.
        if isinstance(value, str) and value.lstrip().startswith(tuple(self.DANGEROUS_PREFIXES)):
            return "'" + value
        return value

    @staticmethod
    def _arabic_or_blank(value) -> str:
        """Arabic column value, or ``''`` — never English dressed as Arabic.

        ``title_ar`` is NOT NULL, so "missing" has to be stored as the empty
        string. The storefront already resolves that honestly with
        ``(lang === 'ar' && title_ar) || title``; what it cannot resolve is an
        English string sitting in an Arabic field, which is what the previous
        ``row.get('title_ar') or row['title']`` produced.
        """
        text = (value or '').strip() if isinstance(value, str) else ''
        return text

    def _normalize(self, source, target_store_id=None):
        # Remap aliases to canonical field names
        mapped = {}
        for k, v in source.items():
            if k is None:
                continue
            canonical_key = self.HEADER_ALIASES.get(k.strip().lower(), k.strip())
            mapped[canonical_key] = v

        row = {k: v.strip() if isinstance(v, str) else v for k, v in mapped.items()}
        for field, default in dict(size='M', stock_level='0', currency='EGP',
                                   color=row.get('color_family', ''), sku_code='').items():
            if row.get(field) in (None, ''):
                row[field] = default

        # If color_family was not provided in source at all but color provided, derive color_family
        if 'color_family' not in source and row.get('color'):
            row['color_family'] = row['color']

        # Resolve category if given as name or name_ar instead of raw slug
        slug = row.get('category_slug')
        if slug:
            cat = self.db.query(Category).filter(
                (Category.slug == slug) |
                (Category.name.ilike(slug)) |
                (Category.name_ar == slug)
            ).first()
            if cat:
                row['category_slug'] = cat.slug

        if target_store_id and not row.get('store_id') and not row.get('branch_id'):
            row['store_id'] = target_store_id

        return row

    def _validate_row(self, row: Dict[str, Any], row_num: int, brand_id: Optional[int] = None) -> List[CatalogImportError]:
        errors = []
        def error(field, message, suggestion=None):
            errors.append(CatalogImportError(row_num, field, message, row.get(field), suggestion))

        for field in self.REQUIRED_FIELDS:
            if row.get(field) is None or str(row[field]).strip() == '':
                error(field, f'Missing required field: {field}', f'Provide a valid value for {field}')

        for field, limit in self.LIMITS.items():
            value = row.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                error(field, f'Must be text of at most {limit} characters', f'Shorten text to <= {limit} chars')

        for field in ('base_price', 'price_override', 'compare_at_price'):
            if row.get(field) not in (None, ''):
                try:
                    value = validate_money(row[field], field, allow_zero=False, required=True, exact_scale=True)
                    if value > BrandRepository.MAX_SKU_PRICE:
                        error(field, 'Price exceeds maximum', f'Price must be <= {BrandRepository.MAX_SKU_PRICE}')
                except (ValueError, TypeError):
                    error(field, 'Price must be finite, positive and have at most two decimal places', 'Enter a decimal price like 850.00')

        if row.get('compare_at_price') not in (None, '') and row.get('base_price') not in (None, ''):
            try:
                _was = validate_money(row['compare_at_price'], 'compare_at_price', allow_zero=False,
                                      required=True, exact_scale=True)
                _now = validate_money(row['base_price'], 'base_price', allow_zero=False,
                                      required=True, exact_scale=True)
                if _was <= _now:
                    error('compare_at_price',
                          'compare_at_price must be greater than base_price — a strike-through '
                          'price that was never higher is not a discount',
                          'Ensure original price is strictly greater than base price')
            except (ValueError, TypeError):
                pass

        value = row.get('stock_level', 0)
        if isinstance(value, bool) or not re.fullmatch(r'\d{1,6}', str(value)) or not 0 <= int(value) <= 100000:
            error('stock_level', 'Stock must be a whole number between 0 and 100000', 'Enter a non-negative integer like 25')

        sku = row.get('sku_code')
        if sku and (not isinstance(sku, str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,100}', sku)):
            error('sku_code', 'SKU must contain 3–100 letters, digits, hyphens or underscores', 'Use alphanumeric characters and hyphens')

        slug = row.get('category_slug')
        if isinstance(slug, str) and slug and not self.db.query(Category.id).filter(Category.slug == slug).first():
            error('category_slug', f'Category "{slug}" not found',
                          'Select a seeded category: ' + ', '.join(self.SEEDED_CATEGORY_SLUGS))

        url = row.get('thumbnail_url')
        if isinstance(url, str) and url:
            try:
                parsed = urlsplit(url)
                if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError()
            except ValueError:
                error('thumbnail_url', 'A public HTTP(S) image URL without credentials is required', 'Provide a public HTTPS link')

        if not isinstance(row.get('currency'), str) or not re.fullmatch(r'[A-Z]{3}', row['currency']):
            error('currency', 'Use a three-letter uppercase currency code', 'Use standard ISO code such as EGP or USD')

        # Branch store isolation check
        target_store = row.get('store_id') or row.get('branch_id')
        if target_store and brand_id:
            try:
                s_id = int(target_store)
                st = self.db.query(StoreLocation).filter_by(id=s_id).first()
                if st and st.brand_id != brand_id:
                    error('store_id', f'Store #{s_id} belongs to another brand; tenant isolation violation', 'Assign only stores owned by your brand')
            except (ValueError, TypeError):
                error('store_id', 'Store ID must be a valid integer', 'Provide an integer store ID')

        for field in ('style_tags', 'occasion_tags', 'images'):
            val = row.get(field)
            if val in (None, ''):
                row[field] = '[]'
                continue
            try:
                if isinstance(val, str):
                    val = json.loads(val) if val.startswith('[') else val.split(',')
                if not isinstance(val, list) or len(val) > 100 or any(not isinstance(v, str) or len(v) > 1000 for v in val):
                    raise ValueError()
                encoded = json.dumps(val, ensure_ascii=False)
                if len(encoded) > 5000:
                    raise ValueError()
                row[field] = encoded
            except (ValueError, TypeError):
                error(field, 'Must be a bounded array of strings or comma-separated text', 'Use comma-separated tags')

        for field in ('dominant_hex', 'color_hex'):
            if row.get(field) and (not isinstance(row[field], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', row[field])):
                error(field, 'Must be a six-digit hex color', 'Use #RRGGBB format like #1B1F3B')

        return errors

    def _generate_sku_code(self, product_title, size, color, brand_slug):
        identity = json.dumps([brand_slug, product_title, size, color], ensure_ascii=False)
        return 'SKU-' + hashlib.sha256(identity.encode()).hexdigest()[:32].upper()

    def _prepare_rows(self, rows, brand_id, target_store_id=None):
        valid, errors, seen, duplicate = [], [], set(), 0
        brand = self.brand_repo.get_by_id(brand_id)
        if not brand:
            raise ValueError('Brand not found')
        for number, source in enumerate(rows, 2):
            if not isinstance(source, dict) or None in source:
                errors.append(CatalogImportError(number, 'row', 'Row has invalid structure or extra columns'))
                continue
            row = self._normalize(source, target_store_id=target_store_id)
            row_errors = self._validate_row(row, number, brand_id=brand_id)
            if row_errors:
                errors.extend(row_errors)
                continue
            row['_generated_sku'] = not bool(row.get('sku_code'))
            code = row.get('sku_code') or self._generate_sku_code(row['title'], row['size'], row['color'], brand.slug)
            if code in seen:
                errors.append(CatalogImportError(number, 'sku_code', 'Duplicate SKU in file', code, 'Each SKU in the CSV must be unique'))
                duplicate += 1
                continue
            seen.add(code)
            row['sku_code'], row['_row_number'] = code, number
            valid.append(row)
        return valid, errors, dict(total=len(rows), accepted=len(valid),
                                  rejected=len({e.row for e in errors}), duplicate=duplicate)

    def _diagnose_header(self, fields: List[str]) -> Optional[str]:
        """Explain what is actually wrong with a header row, or return None if it is fine."""
        required = list(self.REQUIRED_FIELDS)
        if not fields:
            return ('The file has no header row. The first line must name the columns: '
                    + ', '.join(required))

        if len(fields) == 1 and any(d in fields[0] for d in (';', '\t', '|')):
            delimiter = next(d for d in (';', '\t', '|') if d in fields[0])
            name = {';': 'semicolons', '\t': 'tabs', '|': 'pipes'}[delimiter]
            return (f'The columns look separated by {name}, not commas. Re-save the file as '
                    f'"CSV (comma delimited)" -- in Excel use File > Save As and pick that '
                    f'exact format.')

        duplicates = sorted({f for f in fields if fields.count(f) > 1})
        if duplicates:
            return ('These column names appear more than once: ' + ', '.join(duplicates)
                    + '. Every column must have a unique name.')

        missing = [f for f in required if f not in fields]
        if not missing:
            return None

        lookup = {f.strip().lower(): f for f in fields}

        if all(lookup.get(f) not in (None, f) for f in missing):
            if all((lookup.get(f) or '').strip().lower() == f
                   and (lookup.get(f) or '') == (lookup.get(f) or '').strip()
                   for f in missing) and len(missing) > 1:
                return ('The column names are in the wrong case. Header names must be '
                        'lowercase: ' + ', '.join(required))
            if all((lookup.get(f) or '').strip() != (lookup.get(f) or '') for f in missing) and len(missing) > 1:
                return ('The column names have extra spaces around them. Remove the spaces so '
                        'the header reads exactly: ' + ', '.join(required))

        hints, unresolved = [], []
        for field in missing:
            candidate = lookup.get(field)
            if candidate is not None and candidate != field:
                if candidate.strip() != candidate:
                    hints.append(f'"{candidate}" has extra spaces around it -- rename it to "{field}"')
                else:
                    hints.append(f'"{candidate}" is the wrong case -- rename it to "{field}" (lowercase)')
                continue
            close = difflib.get_close_matches(field, fields, n=1, cutoff=0.75)
            if close:
                hints.append(f'"{close[0]}" looks like a misspelling of "{field}"')
            else:
                unresolved.append(field)

        parts = []
        if unresolved:
            parts.append('Missing required column(s): ' + ', '.join(unresolved))
        if hints:
            parts.append('; '.join(hints))

        if unresolved and not hints and len(unresolved) == len(required):
            return ('This does not look like a product catalog file -- none of the required '
                    'columns are present. Expected: ' + ', '.join(required)
                    + '. Found: ' + ', '.join(fields[:8])
                    + (', ...' if len(fields) > 8 else ''))
        return '. '.join(parts) + '.'

    def parse_csv(self, csv_content, brand_id, target_store_id=None) -> Tuple[list, list, dict]:
        try:
            reader = csv.DictReader(io.StringIO(csv_content.lstrip('\ufeff')), strict=True)
            fields = reader.fieldnames or []
            problem = self._diagnose_header(fields)
            if problem:
                # Only try alias resolution if the problem is not a structural case/whitespace/delimiter/duplicate error
                if not any(k in problem.lower() for k in ("wrong case", "extra spaces", "separated by", "more than once")):
                    has_known_alias = any(f.strip().lower() in self.HEADER_ALIASES for f in fields)
                    if has_known_alias:
                        canonical_fields = [self.HEADER_ALIASES.get(f.strip().lower(), f.strip().lower()) for f in fields]
                        if any(f.strip().lower() == 'color' for f in fields) and 'color_family' not in canonical_fields:
                            canonical_fields.append('color_family')
                        canonical_problem = self._diagnose_header(canonical_fields)
                        if not canonical_problem:
                            problem = None
            if problem:
                raise CatalogHeaderError(problem)
            rows = []
            for source in reader:
                if len(rows) >= self.MAX_ROWS:
                    raise ValueError(f'At most {self.MAX_ROWS} rows per import')
                rows.append({k: self._sanitize_csv_value(v) if k in ('title', 'title_ar', 'description', 'description_ar', 'product_name') else v for k, v in source.items() if k is not None})
            if not rows:
                raise ValueError('CSV contains no data rows')
            return self._prepare_rows(rows, brand_id, target_store_id=target_store_id)
        except (csv.Error, ValueError) as exc:
            field = 'header' if isinstance(exc, CatalogHeaderError) else 'file'
            return [], [CatalogImportError(0, field, str(exc))], dict(total=0, accepted=0, rejected=0, duplicate=0)

    def preview_csv(self, csv_content: str, brand_id: int, target_store_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Parses and validates CSV content without database writes.
        Returns total rows, counts, preview records, errors, and warnings.
        """
        valid_rows, errors, stats = self.parse_csv(csv_content, brand_id, target_store_id=target_store_id)
        error_rows = {e.row for e in errors}
        total_rows = stats.get('total', 0)
        accepted_rows = stats.get('accepted', 0)

        # Build preview items
        preview_records = []
        for row in valid_rows[:50]:
            code = row.get('sku_code')
            existing_sku = self.db.query(ProductSKU).filter_by(sku_code=code).first()
            action = "update" if existing_sku else "create"
            preview_records.append({
                "row_number": row.get('_row_number'),
                "status": "valid",
                "action": action,
                "product_name": row.get('title'),
                "sku": code,
                "category": row.get('category_slug'),
                "price": str(row.get('base_price')),
                "original_price": str(row.get('compare_at_price')) if row.get('compare_at_price') else None,
                "currency": row.get('currency', 'EGP'),
                "stock": row.get('stock_level'),
                "size": row.get('size'),
                "color": row.get('color'),
                "thumbnail_url": row.get('thumbnail_url'),
                "branch_id": row.get('store_id'),
            })

        # Add failed rows to preview with error status
        for err in errors[:20]:
            if err.row > 0 and err.row not in [p.get("row_number") for p in preview_records]:
                preview_records.append({
                    "row_number": err.row,
                    "status": "error",
                    "action": "error",
                    "product_name": "—",
                    "sku": str(err.value or "—") if err.field == "sku_code" else "—",
                    "category": "—",
                    "price": "—",
                    "currency": "EGP",
                    "stock": 0,
                    "size": "—",
                    "color": "—",
                    "thumbnail_url": "",
                    "branch_id": None,
                    "error_message": f"{err.field}: {err.message}",
                })

        preview_records.sort(key=lambda x: x.get("row_number", 0))

        return {
            "total_rows": total_rows,
            "valid_rows_count": accepted_rows,
            "error_rows_count": len(error_rows),
            "warning_rows_count": 0,
            "duplicate_rows_count": stats.get('duplicate', 0),
            "can_import": accepted_rows > 0,
            "preview_records": preview_records,
            "errors": [e.to_dict() for e in errors],
            "warnings": [],
        }

    def import_products(self, valid_rows, brand_id, target_store_id=None):
        accepted, rejected, errors = 0, 0, []
        new_products_created = []
        # Rows accepted without an Arabic title. Reported, never hidden: the
        # column stays empty (see _arabic_or_blank), so the storefront falls
        # back to English visibly rather than claiming a translation exists.
        missing_title_ar = []
        media_registered = 0

        for fallback_number, row in enumerate(valid_rows, 2):
            number = row.get('_row_number', fallback_number)
            try:
                brand = self.db.query(BrandProfile).filter_by(id=brand_id).with_for_update().first()
                if not brand:
                    raise ValueError('Brand not found')
                category = self.db.query(Category).filter_by(slug=row['category_slug']).first()
                if not category:
                    raise ValueError('Category not found')
                code = row.get('sku_code') or self._generate_sku_code(row['title'], row.get('size', 'M'), row.get('color', row['color_family']), brand.slug)
                sku = self.db.query(ProductSKU).filter_by(sku_code=code).with_for_update().first()
                product = self.db.query(Product).filter_by(brand_id=brand_id, title=row['title']).first()
                is_brand_new = False
                if not sku and product and row.get('_generated_sku'):
                    matches = self.db.query(ProductSKU).filter_by(product_id=product.id,
                        size=row['size'], color=row['color']).with_for_update().all()
                    if len(matches) > 1:
                        raise ValueError('Ambiguous variant: provide an explicit sku_code')
                    sku = matches[0] if matches else None
                if sku and (not product or sku.product_id != product.id):
                    raise ValueError('SKU already assigned to another product; reassignment is not allowed')
                if not product:
                    slug = 'brand-' + str(brand_id) + '-' + hashlib.sha256(row['title'].encode()).hexdigest()[:24]
                    # The Arabic columns are NOT NULL, and the previous code
                    # copied the English title into them when no translation was
                    # supplied. That is a silent falsehood: the row then claims
                    # an Arabic title exists, and an English string renders
                    # inside an RTL storefront with nothing marking it as
                    # untranslated. Missing Arabic is stored as MISSING (empty),
                    # which the storefront already resolves honestly with
                    # `(lang === 'ar' && title_ar) || title`.
                    product = Product(brand_id=brand_id, category_id=category.id, title=row['title'], slug=slug,
                                      title_ar=self._arabic_or_blank(row.get('title_ar')), description=row.get('description') or row['title'],
                                      description_ar=row.get('description_ar') or row.get('description') or row['title'],
                                      rating=0, review_count=0, style_compatibility_base=0)
                    self.db.add(product)
                    is_brand_new = True
                product.category_id = category.id
                product.base_price = validate_money(row['base_price'], 'base_price', allow_zero=False, required=True, exact_scale=True)
                if 'compare_at_price' in row:
                    product.compare_at_price = (
                        validate_money(row['compare_at_price'], 'compare_at_price', allow_zero=False,
                                       required=True, exact_scale=True)
                        if row.get('compare_at_price') not in (None, '') else None
                    )
                for field in ('color_family', 'thumbnail_url', 'currency', 'material', 'dominant_hex', 'title_ar', 'description', 'description_ar', 'style_tags', 'occasion_tags', 'images'):
                    if row.get(field) not in (None, ''):
                        setattr(product, field, row[field])
                self.db.flush()
                if not sku:
                    sku = ProductSKU(product_id=product.id, sku_code=code, brand_id=brand_id)
                    self.db.add(sku)
                sku.size = row.get('size') or 'M'
                sku.color = row.get('color') or row['color_family']
                sku.stock_level = int(row.get('stock_level') or 0)
                sku.is_in_stock = sku.stock_level > 0
                sku.brand_id = brand_id
                if row.get('price_override') not in (None, ''):
                    sku.price_override = validate_money(row['price_override'], 'price_override', allow_zero=False, required=True, exact_scale=True)
                if row.get('color_hex'):
                    sku.color_hex = row['color_hex']
                self.db.flush()

                # Store location & store inventory mapping with tenant isolation
                store = None
                store_target = row.get('store_id') or row.get('branch_id') or target_store_id
                if store_target:
                    try:
                        s_id = int(store_target)
                        store = self.db.query(StoreLocation).filter_by(id=s_id, brand_id=brand_id).first()
                        if not store:
                            raise ValueError(f"Store #{s_id} not found or does not belong to your brand.")
                    except (ValueError, TypeError) as e:
                        if "not belong" in str(e):
                            raise
                elif row.get('branch_name') or row.get('store_name'):
                    name_cand = (row.get('branch_name') or row.get('store_name')).strip()
                    store = self.db.query(StoreLocation).filter(
                        StoreLocation.brand_id == brand_id,
                        StoreLocation.name.ilike(name_cand)
                    ).first()

                if store:
                    st_inv = self.db.query(StoreInventory).filter_by(store_id=store.id, sku_id=sku.id).with_for_update().first()
                    if not st_inv:
                        st_inv = StoreInventory(
                            store_id=store.id,
                            sku_id=sku.id,
                            brand_id=brand_id,
                            quantity=sku.stock_level,
                            reserved_quantity=0,
                        )
                        self.db.add(st_inv)
                    else:
                        st_inv.quantity = sku.stock_level

                self.db.commit()

                # Close the gap this turn exists for: an imported product used
                # to get a thumbnail_url and NOTHING in product_images, so the
                # storefront had no registered hero and the card fell back to a
                # hotlink (or to "Image unavailable"). Best-effort by design —
                # the product is already committed, so a media failure must not
                # reject a valid catalogue row; it is logged and counted.
                media_rows = self._materialize_media(product, row)
                if media_rows:
                    media_registered += media_rows

                accepted += 1
                if is_brand_new and not (row.get('title_ar') or '').strip():
                    missing_title_ar.append({'row': number, 'title': product.title})
                if is_brand_new:
                    new_products_created.append({
                        "id": product.id,
                        "title": product.title,
                        "name": product.title,
                        "price": str(product.base_price),
                        "currency": product.currency,
                        "thumbnail_url": product.thumbnail_url,
                    })
            except (ValueError, IntegrityError) as exc:
                self.db.rollback()
                message = str(exc) if isinstance(exc, ValueError) else 'Catalog conflict; verify SKU uniqueness and retry'
                errors.append(CatalogImportError(number, 'row', message).to_dict())
                rejected += 1
            except Exception:
                self.db.rollback()
                logger.error('catalog_import_row_failed', row=number)
                raise
        return accepted, rejected, errors, new_products_created, missing_title_ar, media_registered

    def _materialize_media(self, product, row) -> int:
        """Register product_images for an imported product. Returns rows written.

        Returns 0 — never raises — when the import cannot lawfully or physically
        materialise a picture:
          * no thumbnail_url on the row;
          * the host is not an approved commercial source (Unsplash/Pexels);
          * object storage is not configured in this environment (the test
            suite and local dev run without a bucket).
        A caller can therefore tell "registered N assets" from "registered
        nothing" via the job result, and the storefront falls back to the legacy
        URL instead of being told a registered image exists when it does not.
        """
        source_url = (row.get('thumbnail_url') or '').strip()
        if not source_url:
            return 0
        try:
            from backend.app.services.media_materialization_service import (
                MediaMaterializationService, MediaMaterializationError,
                MediaSourceNotApproved, provider_for_url,
            )
            provider = provider_for_url(source_url)
            service = MediaMaterializationService(self.db)
            try:
                service._get_storage()
            except Exception as exc:  # unconfigured storage is a skip, not a failure
                logger.info('catalog_import_media_skipped', product_id=product.id, reason=type(exc).__name__)
                return 0
            images = row.get('images') or ''
            source_ref = source_url
            if isinstance(images, str) and images.startswith('['):
                try:
                    parsed = json.loads(images)
                    if isinstance(parsed, list) and parsed:
                        source_ref = str(parsed[0])
                except (TypeError, ValueError):
                    pass
            rows = service.materialize(
                product,
                source_url,
                source_type='stock',
                provider=provider,
                source_ref=source_ref,
                attribution=f"Photo: {provider.capitalize()}",
            )
            return len(rows)
        except MediaSourceNotApproved as exc:
            logger.info('catalog_import_media_not_approved', product_id=product.id, reason=str(exc))
            return 0
        except MediaMaterializationError as exc:
            logger.error('catalog_import_media_failed', product_id=product.id, reason=str(exc))
            return 0
        except Exception as exc:  # defensive: media must never break an import
            logger.error('catalog_import_media_error', product_id=getattr(product, 'id', None), reason=type(exc).__name__)
            return 0

    def _process(self, brand_id, file_name, file_size, prepare, actor_id=None, target_store_id=None, send_notifications=False):
        job = self.brand_repo.create_import_job(brand_id, file_name, file_size)
        job_id = job.id
        try:
            job.status, job.started_at = 'processing', datetime.now(timezone.utc)
            self.db.commit()
            valid, validation_errors, stats = prepare()
            accepted, rejected, import_errors, new_prods, missing_ar, media_rows = self.import_products(valid, brand_id, target_store_id=target_store_id)
            errors = [e.to_dict() for e in validation_errors] + import_errors
            job.total_rows, job.accepted_rows = stats['total'], accepted
            job.rejected_rows = stats['rejected'] + rejected
            job.duplicate_rows = stats['duplicate']
            job.status = 'completed' if accepted and not errors else 'partially_completed' if accepted else 'failed'
            job.errors_json, job.completed_at = json.dumps(errors), datetime.now(timezone.utc)
            self.db.add(AuditLog(user_id=actor_id, action='BRAND_CATALOG_IMPORTED', resource_type='CatalogImportJob',
                                 resource_id=str(job_id), details_json=json.dumps(dict(brand_id=brand_id, accepted=accepted, rejected=job.rejected_rows))))
            self.db.commit()

            # Dispatch automated email notifications to eligible customers
            notif_result = {"queued": 0, "recipients_count": 0}
            if send_notifications and new_prods and accepted > 0:
                notif_result = self.dispatch_import_notifications(brand_id, job_id, new_prods, branch_id=target_store_id)

            return dict(
                job_id=job.id,
                status=job.status,
                total_rows=job.total_rows,
                accepted_rows=job.accepted_rows,
                rejected_rows=job.rejected_rows,
                duplicate_rows=job.duplicate_rows,
                notifications_queued=notif_result.get("queued", 0),
                notification_recipients_count=notif_result.get("recipients_count", 0),
                # Honest completeness signal: rows created without Arabic copy.
                rows_missing_title_ar=len(missing_ar),
                media_rows_registered=media_rows,
                missing_title_ar_rows=[m['row'] for m in missing_ar][:50],
                errors=errors[:50]
            )
        except Exception:
            self.db.rollback()
            job = self.brand_repo.get_import_job(job_id, brand_id)
            if job:
                job.status, job.completed_at = 'failed', datetime.now(timezone.utc)
                job.errors_json = json.dumps([CatalogImportError(0, 'system', 'Import interrupted; inspect catalog before retrying').to_dict()])
                self.db.commit()
            raise

    def process_csv_import(self, csv_content, brand_id, file_name=None, actor_id=None, target_store_id=None, send_notifications=False):
        return self._process(
            brand_id,
            file_name,
            len(csv_content.encode()),
            lambda: self.parse_csv(csv_content, brand_id, target_store_id=target_store_id),
            actor_id=actor_id,
            target_store_id=target_store_id,
            send_notifications=send_notifications,
        )

    def process_json_import(self, products, brand_id, actor_id=None, target_store_id=None, send_notifications=False):
        return self._process(
            brand_id,
            'api_import.json',
            None,
            lambda: self._prepare_rows(products, brand_id, target_store_id=target_store_id),
            actor_id=actor_id,
            target_store_id=target_store_id,
            send_notifications=send_notifications,
        )

    def dispatch_import_notifications(
        self,
        brand_id: int,
        job_id: int,
        new_products: List[Dict[str, Any]],
        branch_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches automated email notifications about newly published products
        to eligible users (customers with marketing consent).
        Idempotent via unique EmailOutbox event_key per user per job.
        Never raises: email transport failures are logged and recorded honestly.
        """
        if not new_products:
            return {"queued": 0, "recipients_count": 0}

        brand = self.db.query(BrandProfile).filter_by(id=brand_id).first()
        if not brand:
            return {"queued": 0, "recipients_count": 0}

        branch_name = None
        if branch_id:
            store = self.db.query(StoreLocation).filter_by(id=branch_id, brand_id=brand_id).first()
            if store:
                branch_name = store.name

        try:
            from backend.app.models.user import User, UserRole
            from backend.app.models.email_preference import EmailPreference
            from backend.app.models.email_outbox import EmailOutbox
            from backend.app.services.email_consent import unsubscribe_url_for
            from backend.app.services.email_service import render_new_arrivals_email, send_email, is_email_configured

            users = self.db.query(User).filter(
                User.is_active == True,
                User.is_verified == True,
            ).all()

            eligible_users = []
            for u in users:
                # Include consumer or customer roles
                u_role = getattr(u.role, 'value', str(u.role)).lower()
                if u_role not in ('consumer', 'customer', 'brand_owner'):
                    continue
                pref = self.db.query(EmailPreference).filter_by(user_id=u.id).first()
                if pref is None or pref.marketing is True:
                    eligible_users.append(u)

            queued = 0
            sent = 0
            failed = 0
            skipped = 0

            # Dispatch bounded batch of notification emails
            for u in eligible_users[:50]:
                event_key = f"import:{job_id}:user:{u.id}:arrivals"
                existing = self.db.query(EmailOutbox).filter_by(event_key=event_key).first()
                if existing:
                    skipped += 1
                    continue

                unsub_url = unsubscribe_url_for(u.id, "marketing")
                subject, html, text = render_new_arrivals_email(
                    brand_name=brand.brand_name,
                    brand_slug=brand.slug,
                    products=new_products,
                    branch_name=branch_name,
                    unsubscribe_url=unsub_url,
                )

                outbox = EmailOutbox(
                    event_key=event_key,
                    template="new_arrivals",
                    locale=u.preferred_language or "en",
                    recipient=u.email,
                    status="pending",
                )
                self.db.add(outbox)
                self.db.commit()

                if is_email_configured():
                    try:
                        res = send_email(
                            to=u.email,
                            subject=subject,
                            html=html,
                            text=text,
                            headers={"List-Unsubscribe": f"<{unsub_url}>"},
                        )
                        outbox.status = "sent"
                        outbox.message_id = res.get("message_id")
                        sent += 1
                    except Exception as exc:
                        outbox.status = "failed"
                        outbox.last_error = str(exc)[:500]
                        failed += 1
                    self.db.commit()
                else:
                    queued += 1

            return {
                "queued": queued + sent,
                "sent": sent,
                "failed": failed,
                "skipped": skipped,
                "recipients_count": len(eligible_users),
            }
        except Exception as e:
            logger.warning("email_notification_dispatch_failed", err=str(e))
            return {"queued": 0, "recipients_count": 0, "error": str(e)}

    @staticmethod
    def generate_sample_csv() -> str:
        """Downloadable official CSV sample template matching CONFIT_A schema."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "product_name", "sku", "description", "category",
            "price", "currency", "original_price", "color",
            "size", "stock_quantity", "image_url"
        ])
        writer.writerow([
            "Classic Cotton Shirt", "CONFIT-SHIRT-001",
            "Regular fit crisp cotton shirt with spread collar", "tops",
            "850.00", "EGP", "1000.00", "White", "M", "25",
            "https://images.pexels.com/photos/297933/pexels-photo-297933.jpeg"
        ])
        writer.writerow([
            "Linen Summer Trousers", "CONFIT-TROUSERS-002",
            "Tailored breathable linen blend trousers", "bottoms",
            "1200.00", "EGP", "1200.00", "Beige", "L", "12",
            "https://images.pexels.com/photos/1598507/pexels-photo-1598507.jpeg"
        ])
        writer.writerow([
            "Minimal Leather Belt", "CONFIT-BELT-003",
            "Hand-stitched genuine leather belt with brass buckle", "accessories",
            "650.00", "EGP", "650.00", "Black", "One Size", "18",
            "https://images.pexels.com/photos/1598508/pexels-photo-1598508.jpeg"
        ])
        writer.writerow([
            "Tailored Wool Blazer", "CONFIT-BLAZER-004",
            "Single-breasted Italian virgin wool blazer", "outerwear",
            "2450.00", "EGP", "2800.00", "Navy", "48", "8",
            "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"
        ])
        return output.getvalue()

    @staticmethod
    def generate_error_report_csv(errors: List[Dict[str, Any]]) -> str:
        """
        Exports row-level validation errors to CSV with spreadsheet formula
        injection defense (prefixing single quote on =, +, -, @).
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Row Number", "Field", "Submitted Value", "Error Reason", "Corrective Action"])
        DANGEROUS = ('=', '+', '-', '@', '\t', '\r')
        for err in errors:
            row_num = err.get("row", 0)
            field = err.get("field", "general")
            val = str(err.get("value", "") or "")
            if val.startswith(DANGEROUS):
                val = "'" + val
            msg = err.get("message", "Validation error")
            suggestion = err.get("suggestion", "")
            if not suggestion:
                if field in ("base_price", "price"):
                    suggestion = "Enter a positive numeric price with up to 2 decimal places (e.g. 850 or 1200.50)"
                elif field in ("sku_code", "sku"):
                    suggestion = "Use 3-100 alphanumeric characters, hyphens or underscores (e.g. CONFIT-001)"
                elif field in ("category_slug", "category"):
                    suggestion = "Use an existing category slug like outerwear, shirts, trousers, knitwear, accessories"
                elif field in ("stock_level", "stock_quantity"):
                    suggestion = "Enter an integer between 0 and 100000"
                elif field in ("thumbnail_url", "image_url"):
                    suggestion = "Enter a valid public http(s) URL pointing to an image"
                else:
                    suggestion = f"Verify {field} matches the required catalog format"
            writer.writerow([row_num, field, val, msg, suggestion])
        return output.getvalue()
