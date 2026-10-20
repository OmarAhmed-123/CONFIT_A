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


#: What each media verdict means for the person holding the CSV.
_MEDIA_REASONS = {
    'no_source': 'no image_url was supplied',
    'source_not_approved': ('the image host is not an approved stock source; use '
                            'images.unsplash.com or images.pexels.com, or declare image_source=own'),
    'own_images_disabled': ('your own photography is not enabled for CSV import on this '
                            'deployment; upload the image in the brand dashboard instead'),
    'storage_unavailable': ('this deployment has no object storage configured, so no image can '
                            'be registered; an operator must configure storage first'),
    'materialization_failed': ('the image could not be downloaded, decoded or stored; check the '
                               'URL is a public direct link to a JPEG/PNG/WebP file'),
    'object_missing': 'the stored image is missing from object storage; retry the import',
    'legacy_label_key': 'the existing image registration is unreadable; supply image_url again',
}


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
    #: Every column the importer actually understands. This used to be an
    #: advisory list nothing read, which is how a column could be named in a CSV
    #: and silently dropped — a brand owner who typed ``materiel`` got no error
    #: and no material. It is now the whitelist behind the "unrecognised column"
    #: warning, so it must stay honest about what is read.
    OPTIONAL_FIELDS = ['title_ar', 'description', 'description_ar', 'material', 'care_instructions',
                       'gender', 'currency', 'compare_at_price', 'style_tags', 'occasion_tags',
                       'images', 'image_source', 'sku_code', 'size', 'color', 'stock_level',
                       'price_override', 'dominant_hex', 'color_hex', 'store_id', 'branch_id',
                       'branch_name', 'branch_slug', 'store_name']
    DANGEROUS_PREFIXES = ['=', '+', '-', '@', '\t', '\r']
    LIMITS = dict(title=255, title_ar=255, description=2000, description_ar=2000,
                  material=255, care_instructions=500, color_family=50, thumbnail_url=1000,
                  size=20, color=50, sku_code=100, category_slug=100, gender=16, image_source=8)

    #: ``image_source`` accepts only these. Empty means "decide from the host":
    #: an approved stock host is ``stock``; anything else is refused unless the
    #: row asserts first-party rights with ``image_source=own``.
    IMAGE_SOURCES = ('stock', 'own')

    #: Words a human writes in a spreadsheet, mapped onto the three values the
    #: stylist understands (``services/styling/garment_gender``).
    GENDER_SYNONYMS = {
        'men': 'mens', 'man': 'mens', 'male': 'mens', 'mens': 'mens', 'menswear': 'mens',
        'gents': 'mens', 'gentlemen': 'mens', 'رجالي': 'mens',
        'women': 'womens', 'woman': 'womens', 'female': 'womens', 'womens': 'womens',
        'womenswear': 'womens', 'ladies': 'womens', 'ladys': 'womens', 'نسائي': 'womens',
        'unisex': 'unisex', 'all': 'unisex', 'any': 'unisex', 'both': 'unisex',
        'none': 'unisex', 'للجنسين': 'unisex',
    }

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
        'sex': 'gender',
        'audience': 'gender',
        'target_gender': 'gender',
        'care': 'care_instructions',
        'wash_care': 'care_instructions',
        'img_source': 'image_source',
        'image_source_type': 'image_source',
    }

    def __init__(self, db: Session):
        self.db = db
        self.brand_repo = BrandRepository(db)
        #: Per-run record of photographs that could not be imported. Reset at
        #: the start of every import so a job never reports another job's
        #: failures (the service instance is reused by the caller).
        self._photo_warnings: list = []

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
        for field, default in dict(size='M', stock_level='0', currency=self._pricing_currency(),
                                   color=row.get('color_family', ''), sku_code='').items():
            if row.get(field) in (None, ''):
                row[field] = default

        # If color_family was not provided in source at all but color provided, derive color_family
        if 'color_family' not in source and row.get('color'):
            row['color_family'] = row['color']

        # Gender is stored as exactly one of mens/womens/unisex. A spreadsheet
        # says "Women", " ladies" or "رجالي"; translating that here means the
        # validator, the template and the stylist cannot disagree about it.
        raw_gender = row.get('gender')
        row['_gender_explicit'] = bool(isinstance(raw_gender, str) and raw_gender.strip())
        if row['_gender_explicit']:
            row['gender'] = self.GENDER_SYNONYMS.get(raw_gender.strip().lower(), raw_gender.strip().lower())
        else:
            # No gender column: derive it from the garment noun with the same
            # classifier migration 0027 used to backfill every existing product
            # (`services/styling/garment_gender`). Without this, CSV-imported
            # products would be the ONLY rows in the catalogue whose gender was
            # never inferred — and since import is a brand's primary path, the
            # stylist's gender filter would degrade for the newest stock first.
            # The derived value is reported as `rows_gender_inferred`, and it is
            # only ever written on CREATE, so a human correction is never
            # overwritten by a later re-upload.
            from backend.app.services.styling.garment_gender import infer_gender
            row['gender'] = infer_gender(row.get('title'), row.get('category_slug'))

        raw_source = row.get('image_source')
        if isinstance(raw_source, str) and raw_source.strip():
            row['image_source'] = raw_source.strip().lower()
        else:
            row.pop('image_source', None)

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
        else:
            book = self._pricing_currency()
            if row['currency'] != book:
                # MEASURED, not theoretical (scripts/tooling/verify_catalog_csv_import_e2e.py):
                # a row priced in EGP was stored as 1450.00 with currency=EGP; the
                # product page then rendered "1,450 EGP" because the payload
                # declared EGP, while the cart converted the SAME number from the
                # USD price book and rendered 78,166.03 EGP. One product, two
                # prices, differing by the FX rate — and the shopper is charged
                # the second one. The price book has exactly one denomination, so
                # a row priced in another is refused rather than silently
                # re-interpreted.
                error('currency',
                      f'Prices are stored in {book}, which is the price book denomination; '
                      f'this row declares {row["currency"]}',
                      f'Price the row in {book} (the storefront converts for display), or ask an '
                      f'operator to configure market FX before importing other denominations')

        raw_gender = row.get('gender')
        if raw_gender not in (None, ''):
            # `_normalize` has already folded synonyms; anything still unknown is
            # refused rather than quietly coerced, because the stylist filters on
            # this value and a wrong one hides a garment from half the catalogue.
            if raw_gender not in self.VALID_GENDERS:
                error('gender', f'Gender "{raw_gender}" is not recognised',
                      'Use one of: ' + ', '.join(self.VALID_GENDERS) + ' (men/women also accepted)')

        raw_source = row.get('image_source')
        if raw_source not in (None, '') and raw_source not in self.IMAGE_SOURCES:
            error('image_source', f'image_source "{raw_source}" is not recognised',
                  'Use "stock" for licensed stock photography or "own" for your own product image')

        # The media check used to live only in `import_products`, which meant
        # preview called a row valid and the import then rejected it. A validation
        # screen that disagrees with the commit is worse than no screen: the brand
        # owner confirms a green table and gets a red result. Everything the
        # materialiser needs to refuse is therefore refused HERE, so the two
        # verdicts cannot diverge.
        if isinstance(url, str) and url:
            self._validate_image_source(row, url, error)

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

    #: mens | womens | unisex — the vocabulary `services/styling/garment_gender`
    #: filters on. Kept as a tuple here so a bad CSV value can be reported
    #: against the same list the stylist uses.
    VALID_GENDERS = ('mens', 'womens', 'unisex')

    def _pricing_currency(self) -> str:
        """The ONE denomination `products.base_price` is allowed to be in.

        `pricing_presentation` states the invariant plainly: "the price book
        itself is NEVER mutated … the database keeps one canonical denomination
        (PRICING_CURRENCY)". A per-row currency column is therefore not a
        denomination, it is a label — and a label that disagrees with the number
        beside it is exactly the defect that module exists to remove.
        """
        try:
            from backend.app.core.config import settings
            return (getattr(settings, 'PRICING_CURRENCY', 'USD') or 'USD').strip().upper()
        except Exception:
            return 'USD'

    def _own_images_allowed(self) -> bool:
        """Whether first-party image URLs may be fetched. Owner-controlled."""
        try:
            from backend.app.core.config import settings
            return bool(getattr(settings, 'CATALOG_IMPORT_ALLOW_OWN_IMAGES', False))
        except Exception:  # config must never make validation explode
            return False

    def _validate_image_source(self, row, url, error) -> None:
        """Refuse an image URL the media stage could not materialise.

        Two provenances exist and they are checked by different rules:
          ``stock`` — licensed third-party photography, restricted to the
          media service's commercial-use allowlist;
          ``own``   — the brand's own asset, allowed only when the deployment
          has opted in, and then still routed through `core.net_guard`.

        Raises nothing: every failure is reported through `error(...)` so the
        preview table shows the same field the import would fail on.
        """
        from backend.app.services.media_materialization_service import (
            APPROVED_SOURCE_HOSTS, MediaSourceNotApproved, provider_for_url,
        )
        from backend.app.core.net_guard import UnsafeURLError, assert_public_http_url

        declared = row.get('image_source')
        if declared == 'own':
            if not self._own_images_allowed():
                error('image_source',
                      'First-party image imports are disabled on this deployment',
                      'Upload product photography through the brand dashboard, or use a '
                      'licensed stock URL from ' + ', '.join(APPROVED_SOURCE_HOSTS))
                return
            try:
                assert_public_http_url(url)
            except UnsafeURLError as exc:
                error('thumbnail_url', f'Image URL is not fetchable: {exc}',
                      'Use a public https URL on a normal internet host')
            return

        try:
            provider_for_url(url)
        except MediaSourceNotApproved:
            error('thumbnail_url',
                  'This image host is not an approved stock source',
                  'Use images.unsplash.com or images.pexels.com, or set image_source=own '
                  'to import your own photography (requires the deployment flag)')

    def _row_warnings(self, row) -> List[Dict[str, Any]]:
        """Real warnings for one validated row — reported, never blocking.

        Each of these describes something the import CAN do but the shopper
        will notice, so it is surfaced in the preview instead of being
        discovered after publishing.
        """
        number = row.get('_row_number')
        out: List[Dict[str, Any]] = []

        def warn(field, message):
            out.append({'row': number, 'field': field, 'message': message})

        try:
            stock = int(row.get('stock_level') or 0)
        except (TypeError, ValueError):
            stock = 0
        if stock == 0:
            warn('stock_level',
                 'Stock is 0, so the storefront hides this product until it is stocked '
                 '(the catalogue lists only purchasable items)')

        if not (row.get('title_ar') or '').strip():
            warn('title_ar',
                 'No Arabic title: the Arabic storefront will show the English title and '
                 'this product will not match Arabic search terms')

        if not (row.get('description_ar') or '').strip():
            warn('description_ar',
                 'No Arabic description: the Arabic product page will fall back to the '
                 'English copy')

        if not row.get('_gender_explicit'):
            warn('gender',
                 f'No gender given, so it is inferred from the title as '
                 f'"{row.get("gender") or "unisex"}" — add the gender column to control it')

        return out

    def _unknown_column_warnings(self, fields: List[str]) -> List[Dict[str, Any]]:
        """Warn about columns the importer will ignore.

        Without this a typo'd optional column is invisible: the row validates,
        the product is created, and the value the brand owner typed is simply
        not there. Silence is the one answer that is never acceptable here.
        """
        known = set(self.REQUIRED_FIELDS) | set(self.OPTIONAL_FIELDS) | set(self.HEADER_ALIASES)
        out = []
        for field in fields:
            name = (field or '').strip()
            if not name or name in known or name.lower() in known:
                continue
            out.append({
                'row': 1,
                'field': name,
                'message': (f'Column "{name}" is not part of the import contract and will be '
                            f'ignored. Recognised columns: '
                            + ', '.join(sorted(set(self.REQUIRED_FIELDS) | set(self.OPTIONAL_FIELDS)))),
            })
        return out

    def _generate_sku_code(self, product_title, size, color, brand_slug):
        identity = json.dumps([brand_slug, product_title, size, color], ensure_ascii=False)
        return 'SKU-' + hashlib.sha256(identity.encode()).hexdigest()[:32].upper()

    def _prepare_rows(self, rows, brand_id, target_store_id=None):
        valid, errors, seen, duplicate, warnings = [], [], set(), 0, []
        brand = self.brand_repo.get_by_id(brand_id)
        if not brand:
            raise ValueError('Brand not found')
        for number, source in enumerate(rows, 2):
            if not isinstance(source, dict) or None in source:
                errors.append(CatalogImportError(number, 'row', 'Row has invalid structure or extra columns'))
                continue
            row = self._normalize(source, target_store_id=target_store_id)
            row['_row_number'] = number
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
            # A SKU that already belongs to a DIFFERENT product cannot be
            # imported — `import_products` refuses to reassign it. Checking that
            # here means the preview says so on the row, in the same words,
            # instead of showing "valid" and failing at commit.
            collision = self._sku_collision(code, row, brand_id)
            if collision:
                errors.append(CatalogImportError(number, 'sku_code', collision, code,
                                                 'Reuse the SKU only on its own product row, or use a new SKU'))
                continue
            seen.add(code)
            row['sku_code'] = code
            valid.append(row)
            warnings.extend(self._row_warnings(row))
        return valid, errors, dict(total=len(rows), accepted=len(valid),
                                  rejected=len({e.row for e in errors}), duplicate=duplicate,
                                  warnings=warnings)

    def _sku_collision(self, code: str, row, brand_id: int) -> Optional[str]:
        """Why this SKU may not be imported onto this row, or None."""
        existing = self.db.query(ProductSKU).filter_by(sku_code=code).first()
        if not existing:
            return None
        owner = existing.product
        if owner and owner.brand_id == brand_id and owner.title == row.get('title'):
            return None  # a genuine update of this very product
        where = f'product "{owner.title}"' if owner else 'another product'
        return f'SKU already belongs to {where}; a SKU cannot be moved between products'


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
            valid, errors, stats = self._prepare_rows(rows, brand_id, target_store_id=target_store_id)
            # Header-level findings (unrecognised columns) come first so they
            # read before any per-row note.
            stats['warnings'] = self._unknown_column_warnings(fields) + stats.get('warnings', [])
            return valid, errors, stats
        except (csv.Error, ValueError) as exc:
            field = 'header' if isinstance(exc, CatalogHeaderError) else 'file'
            return [], [CatalogImportError(0, field, str(exc))], dict(
                total=0, accepted=0, rejected=0, duplicate=0, warnings=[])

    def _preview_action(self, row, brand_id: int) -> str:
        """`create` or `update`, decided by the SAME rule the importer applies.

        The previous version asked only "does this sku_code exist?". For a row
        with no sku_code — the common case, because SKUs are generated — that
        answer is always "no", so a re-upload of an existing product was
        labelled `create` and then silently updated it. The preview must not
        guess differently from the write.
        """
        sku = self.db.query(ProductSKU).filter_by(sku_code=row['sku_code']).first()
        if sku:
            owner = sku.product
            return 'update' if owner and owner.brand_id == brand_id and owner.title == row.get('title') else 'create'
        if row.get('_generated_sku'):
            product = self.db.query(Product).filter_by(brand_id=brand_id, title=row.get('title')).first()
            if product:
                match = self.db.query(ProductSKU).filter_by(
                    product_id=product.id, size=row.get('size'), color=row.get('color')).first()
                if match:
                    return 'update'
        return 'create'

    def _blocking_warnings(self) -> List[Dict[str, Any]]:
        """Reasons the import cannot succeed on THIS deployment.

        Media materialisation is mandatory and its storage backend is an
        environment concern, not a data concern: with no object store every
        valid row is rejected at commit. Telling the brand owner after they
        confirm is a dead end, so it is said before they can.
        """
        out: List[Dict[str, Any]] = []
        try:
            from backend.app.services.media_materialization_service import MediaMaterializationService
            MediaMaterializationService(self.db)._get_storage()
        except Exception as exc:
            out.append({
                'row': 0,
                'field': 'storage',
                'message': ('Object storage is not configured on this deployment, so no image '
                            'can be registered and every row would be rejected. Fix storage '
                            f'before importing ({type(exc).__name__}).'),
                'blocking': True,
            })
        if not self._own_images_allowed():
            out.append({
                'row': 0,
                'field': 'image_source',
                'message': ('Rows that use your own photography (image_source=own) will be '
                            'rejected: first-party image imports are disabled on this '
                            'deployment. Stock URLs from Unsplash/Pexels are unaffected.'),
                'blocking': False,
            })
        return out

    def preview_csv(self, csv_content: str, brand_id: int, target_store_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Parses and validates CSV content without database writes.

        This IS the dry run: every check the commit performs runs here, and
        nothing is written. Returns row counts, a per-row record with the
        create/update verdict, field-level errors and real warnings.
        """
        valid_rows, errors, stats = self.parse_csv(csv_content, brand_id, target_store_id=target_store_id)
        error_rows = {e.row for e in errors}
        total_rows = stats.get('total', 0)
        accepted_rows = stats.get('accepted', 0)
        warnings = self._blocking_warnings() + list(stats.get('warnings') or [])
        blocking = [w for w in warnings if w.get('blocking')]

        # Build preview items
        preview_records = []
        for row in valid_rows[:50]:
            code = row.get('sku_code')
            preview_records.append({
                "row_number": row.get('_row_number'),
                "status": "valid",
                "action": self._preview_action(row, brand_id),
                "product_name": row.get('title'),
                "sku": code,
                "category": row.get('category_slug'),
                "price": str(row.get('base_price')),
                "original_price": str(row.get('compare_at_price')) if row.get('compare_at_price') else None,
                "currency": row.get('currency') or self._pricing_currency(),
                "stock": row.get('stock_level'),
                "size": row.get('size'),
                "color": row.get('color'),
                "gender": row.get('gender') or 'unisex',
                "thumbnail_url": row.get('thumbnail_url'),
                # Was `row.get('store_id')`, which is empty whenever the branch
                # was given as branch_id or resolved by name — so the Branch
                # column was blank for rows that DO go to a branch.
                "branch_id": row.get('store_id') or row.get('branch_id') or target_store_id,
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
                    "currency": self._pricing_currency(),
                    "stock": 0,
                    "size": "—",
                    "color": "—",
                    "gender": "—",
                    "thumbnail_url": "",
                    "branch_id": None,
                    "error_message": f"{err.field}: {err.message}",
                })

        preview_records.sort(key=lambda x: x.get("row_number", 0))

        # Row 1 is the header — its notes are file-level, not a data row.
        warning_rows = {w.get('row') for w in warnings if isinstance(w.get('row'), int) and w['row'] > 1}

        return {
            "total_rows": total_rows,
            "valid_rows_count": accepted_rows,
            "error_rows_count": len(error_rows),
            "warning_rows_count": len(warning_rows),
            "duplicate_rows_count": stats.get('duplicate', 0),
            # A blocker means "not one row would land", so the confirm button
            # must stay disabled rather than let the owner discover it.
            "can_import": accepted_rows > 0 and not blocking,
            "blocked_reasons": [w['message'] for w in blocking],
            "preview_records": preview_records,
            "errors": [e.to_dict() for e in errors],
            "warnings": warnings,
        }

    def import_products(self, valid_rows, brand_id, target_store_id=None):
        accepted, rejected, errors = 0, 0, []
        new_products_created = []
        # Rows accepted without Arabic copy, and rows whose gender was derived
        # rather than supplied. Reported, never hidden: the column stays empty
        # (see _arabic_or_blank), so the storefront falls back to English
        # visibly rather than claiming a translation exists.
        missing_title_ar = []
        missing_description_ar = []
        gender_inferred = []
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
                                      title_ar=self._arabic_or_blank(row.get('title_ar')),
                                      description=row.get('description') or row['title'],
                                      # The Arabic description followed the OLD rule that
                                      # `_arabic_or_blank` exists to kill: it fell back to the
                                      # English copy, so every imported product claimed an Arabic
                                      # description and the AR storefront rendered English prose
                                      # with nothing marking it as untranslated. Missing Arabic is
                                      # stored as MISSING; the PDP falls back visibly.
                                      description_ar=self._arabic_or_blank(row.get('description_ar')),
                                      gender=row.get('gender') or 'unisex',
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
                # A gender that was INFERRED from the title is only written on
                # creation: re-uploading a stock CSV must not overwrite a value
                # a merchandiser corrected by hand in the dashboard.
                if row.get('_gender_explicit') or is_brand_new:
                    product.gender = row.get('gender') or 'unisex'
                for field in ('color_family', 'thumbnail_url', 'currency', 'material', 'care_instructions',
                              'dominant_hex', 'title_ar', 'description', 'description_ar',
                              'style_tags', 'occasion_tags', 'images'):
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

                # Close the gap this turn exists for: an imported product used
                # to get a thumbnail_url and NOTHING in product_images, so the
                # storefront had no registered hero and the card fell back to a
                # hotlink (or to "Image unavailable").
                #
                # This runs BEFORE the commit on purpose. If the row cannot end
                # up with media that actually resolves, the whole row rolls back
                # — a product whose hero 404s is the defect, so importing one
                # and reporting success would re-certify the bug. "Resolvable"
                # means a registered row AND an object present in the store AND
                # a key the media route will accept; a DB row alone is not
                # evidence (all 54 legacy rows existed and all 54 404'd).
                media = self._materialize_media(product, row)
                if not media.resolvable:
                    # The reason is translated into what the brand owner can DO.
                    # "(materialization_failed)" told them nothing about which of
                    # six causes applied to their own file.
                    raise ValueError(
                        f"product '{row['title']}' was refused: {_MEDIA_REASONS.get(media.reason, media.reason)} "
                        f"(media: {media.reason})"
                    )
                self.db.commit()
                if media.rows:
                    media_registered += media.rows

                accepted += 1
                if is_brand_new and not (row.get('title_ar') or '').strip():
                    missing_title_ar.append({'row': number, 'title': product.title})
                if is_brand_new and not (row.get('description_ar') or '').strip():
                    missing_description_ar.append({'row': number, 'title': product.title})
                if not row.get('_gender_explicit'):
                    gender_inferred.append({'row': number, 'gender': product.gender})
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
        return (accepted, rejected, errors, new_products_created, missing_title_ar,
                media_registered, missing_description_ar, gender_inferred)

    def _photo_sources(self, row, *, hero_url, default_source_type, default_provider,
                       default_attribution):
        """The ordered list of photographs to register for one row.

        Contract (documented in docs/catalog/CATALOG_CSV_IMPORT.md):

        * ``image_url`` (aliases ``thumbnail_url``/``image``) is the HERO and is
          always position 0 — it is the picture the card renders, so it may not
          be displaced by a gallery entry;
        * the ``images`` column adds the REST of the gallery, in the order the
          brand wrote them, as a JSON array or a comma-separated list;
        * duplicates (the hero repeated in ``images``) collapse, and order is
          preserved so the brand's front/back/detail sequence survives;
        * every entry is subject to the same host allowlist as the hero, so a
          gallery cannot smuggle in a source the hero path would refuse.
        """
        from backend.app.services.media_materialization_service import (
            MediaSourceNotApproved, provider_for_url,
        )

        ordered: list = []
        refused: list = []
        seen: set = set()

        def _add(url: str) -> None:
            url = (url or '').strip()
            if not url or url in seen:
                return
            seen.add(url)
            ordered.append(url)

        _add(hero_url)

        raw = row.get('images')
        if isinstance(raw, str) and raw.strip():
            parsed = None
            if raw.strip().startswith('['):
                try:
                    parsed = json.loads(raw)
                except (TypeError, ValueError):
                    parsed = None
            if isinstance(parsed, list):
                candidates = parsed
            else:
                candidates = raw.split(',')
            for candidate in candidates:
                if isinstance(candidate, str):
                    _add(candidate)

        photos = []
        for url in ordered:
            if url == hero_url:
                source_type, provider, attribution = (
                    default_source_type, default_provider, default_attribution)
            else:
                if default_source_type == 'own':
                    # An ``image_source=own`` row is a statement about the whole
                    # row, not just its hero: a brand's own shoot is one set.
                    source_type, provider, attribution = 'own', 'own', 'Image supplied by the brand'
                else:
                    try:
                        provider = provider_for_url(url)
                    except MediaSourceNotApproved:
                        # An unapproved HOST is refused per photograph, not per
                        # row: the hero already passed the same gate, the rest of
                        # the gallery is fine, and rejecting the whole product
                        # over one bad URL would lose rows the brand can fix by
                        # editing a single cell.
                        refused.append(url)
                        continue
                    source_type, attribution = 'stock', f"Photo: {provider.capitalize()}"
            photos.append({
                'url': url,
                'source_type': source_type,
                'provider': provider,
                'attribution': attribution,
                'source_ref': url,
            })

        for url in refused:
            host = url.split('://', 1)[-1].split('/', 1)[0]
            self._photo_warnings.append({
                'row': row.get('row_number'),
                'field': 'images',
                'message': (f"Image from {host or 'an unapproved host'} was not imported: "
                            f"not an approved image source. Use images.unsplash.com or "
                            f"images.pexels.com, or set image_source=own for your own photography."),
            })
        return photos

    def _materialize_media(self, product, row):
        """Register product_images for an imported product. Returns a verdict.

        Returns a `MediaResolvability` with ``resolvable=False`` — never raises —
        when the import cannot lawfully or physically materialise a picture:
          * no thumbnail_url on the row;
          * the host is not an approved commercial source (Unsplash/Pexels) and
            the row did not declare ``image_source=own``;
          * ``image_source=own`` while the deployment has not opted in;
          * object storage is not configured in this environment.
        A caller can therefore tell "registered N assets" from "registered
        nothing" via the job result, and the storefront falls back to the legacy
        URL instead of being told a registered image exists when it does not.

        IDEMPOTENCY: when the product already holds verified media derived from
        this exact source, nothing is re-fetched, re-cropped or re-uploaded. A
        stock-level correction (the normal reason to re-upload a catalogue) used
        to re-render five ratios x two formats for every row and delete the
        registry rows first, so a failed network call during a routine update
        could take a live product's imagery down with it.
        """
        from backend.app.services.media_materialization_service import (
            CANONICAL_KEY_RE, MediaResolvability, verify_resolvable,
        )
        source_url = (row.get('thumbnail_url') or '').strip()
        if not source_url:
            return MediaResolvability(0, False, 'no_source')

        declared = row.get('image_source')
        if declared == 'own' and not self._own_images_allowed():
            logger.warning('catalog_import_own_image_refused', product_id=product.id)
            return MediaResolvability(0, False, 'own_images_disabled')

        try:
            from backend.app.models.catalog import ProductImage
            from backend.app.services.media_materialization_service import (
                MediaMaterializationService, MediaMaterializationError,
                MediaSourceNotApproved, provider_for_url,
            )
            service = MediaMaterializationService(self.db)
            try:
                storage = service._get_storage()
            except Exception as exc:  # unconfigured storage is a skip, not a failure
                logger.warning('catalog_import_media_storage_unavailable', product_id=product.id, reason=type(exc).__name__)
                return MediaResolvability(0, False, 'storage_unavailable')

            if declared == 'own':
                provider, source_type = 'own', 'own'
                attribution = 'Image supplied by the brand'
            else:
                provider = provider_for_url(source_url)
                source_type, attribution = 'stock', f"Photo: {provider.capitalize()}"

            # EVERY supplied photograph, in the order supplied — not just the
            # hero. The old code parsed the array and used parsed[0], so a brand
            # that supplied front/back/detail had two of the three discarded
            # without a word while the job reported success. Each entry is
            # host-checked here, so a gallery cannot smuggle in a source the
            # hero path would refuse.
            photos = self._photo_sources(row, hero_url=source_url,
                                          default_source_type=source_type,
                                          default_provider=provider,
                                          default_attribution=attribution)

            # IDEMPOTENCY, over the whole gallery: skip only when this product
            # already holds exactly these source photographs, all canonical and
            # resolvable. Comparing the hero alone (the old check) would have
            # declared a two-of-three gallery "already done".
            existing = self.db.query(ProductImage).filter(ProductImage.product_id == product.id).all()
            expected_refs = [p['source_ref'] for p in photos]
            existing_refs = []
            for pos, photo in enumerate(photos):
                rows_for_pos = [r for r in existing if (r.photo_index or 0) == pos]
                if not rows_for_pos:
                    existing_refs = []
                    break
                if not any(CANONICAL_KEY_RE.match(r.storage_key or '') for r in rows_for_pos):
                    existing_refs = []
                    break
                existing_refs.append(rows_for_pos[0].source_ref)
            if existing_refs == expected_refs:
                verdict = verify_resolvable(self.db, product.id, storage=storage)
                if verdict.resolvable:
                    return verdict
            _, failures = service.materialize_photos(
                product,
                photos,
                # The caller owns the transaction. If verification below fails,
                # the product, its SKUs and its media rows must all disappear
                # together — a committed-then-rejected row would be the worst
                # of both worlds: reported as rejected, yet live in the catalog.
                commit=False,
            )
            if failures:
                # A dropped photograph is recorded, never silently skipped: the
                # preview/result payload carries one warning per failed image.
                logger.warning('catalog_import_photos_partial', product_id=product.id,
                               failed=len(failures), supplied=len(photos))
                for failure in failures:
                    self._photo_warnings.append({
                        'row': row.get('row_number'),
                        'field': 'images',
                        'message': (f"Image {failure['position'] + 1} of {len(photos)} was not "
                                    f"imported ({failure['reason']}); the rest of the gallery was."),
                    })
            self.db.flush()
            return verify_resolvable(self.db, product.id, storage=storage)
        except MediaSourceNotApproved as exc:
            logger.warning('catalog_import_media_not_approved', product_id=product.id, reason=str(exc))
            return MediaResolvability(0, False, 'source_not_approved')
        except MediaMaterializationError as exc:
            logger.error('catalog_import_media_failed', product_id=product.id, reason=str(exc))
            return MediaResolvability(0, False, 'materialization_failed')
        except Exception as exc:  # defensive: media must never break an import silently
            logger.error('catalog_import_media_error', product_id=getattr(product, 'id', None), reason=type(exc).__name__)
            return MediaResolvability(0, False, 'materialization_failed')

    def _process(self, brand_id, file_name, file_size, prepare, actor_id=None, target_store_id=None, send_notifications=False):
        job = self.brand_repo.create_import_job(brand_id, file_name, file_size)
        job_id = job.id
        try:
            job.status, job.started_at = 'processing', datetime.now(timezone.utc)
            self._photo_warnings = []
            self.db.commit()
            valid, validation_errors, stats = prepare()
            (accepted, rejected, import_errors, new_prods, missing_ar, media_rows,
             missing_desc_ar, gender_inferred) = self.import_products(valid, brand_id, target_store_id=target_store_id)
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
                # Honest completeness signals, all additive to the existing
                # contract: rows created without Arabic copy, rows whose gender
                # was derived from the title rather than supplied, and the real
                # number of media rows registered.
                rows_missing_title_ar=len(missing_ar),
                rows_missing_description_ar=len(missing_desc_ar),
                media_rows_registered=media_rows,
                rows_gender_inferred=len(gender_inferred),
                missing_title_ar_rows=[m['row'] for m in missing_ar][:50],
                errors=errors[:50],
                # Photographs that were supplied but not imported. Additive and
                # deliberately separate from `errors`: the row landed, the
                # gallery is incomplete, and the two must not be conflated.
                media_warnings=self._photo_warnings[:50],
                photos_not_imported=len(self._photo_warnings),
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
        """The downloadable template: one header, five rows that ACTUALLY validate.

        Two of the four previous sample rows were rejected by the importer's own
        rules — `original_price` was equal to `price` on two of them, and a
        strike-through price that was never higher is refused as a false
        discount claim. A template that fails its own validator teaches the
        brand owner the wrong contract, so every row here is round-trip tested
        (`backend/tests/test_catalog_csv_import_contract.py`).

        The Arabic columns are filled in on purpose: UTF-8 in, UTF-8 out, and a
        template that shows only ASCII quietly implies Arabic is optional
        decoration rather than a first-class field.

        The images are real Pexels URLs of the garment each row names — the
        import refuses a row whose picture cannot be resolved, and it refuses a
        picture that is not the thing being sold just as firmly.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "product_name", "sku", "description", "category", "price", "currency",
            "original_price", "color", "size", "stock_quantity", "image_url",
            "gender", "title_ar", "description_ar", "material", "care_instructions",
        ])
        rows = [
            (["Classic Cotton Shirt", "CONFIT-SHIRT-001",
              "Regular-fit crisp cotton shirt with a classic collar",
              # Priced in the PRICE BOOK denomination, not the display currency:
              # see `_validate_row`'s currency rule. The storefront shows EGP.
              "tops", "27.00", "USD", "33.50", "White", "M", "25",
              "https://images.pexels.com/photos/297933/pexels-photo-297933.jpeg",
              "unisex", "قميص قطني كلاسيكي",
              "قميص قطني بقصة مستقيمة وياقة كلاسيكية، مناسب للعمل والمناسبات اليومية",
              "100% cotton", "Machine wash cold; do not tumble dry"]),
            (["Straight-Leg Indigo Denim", "CONFIT-DENIM-002",
              "Mid-rise straight-leg jeans in a rigid indigo denim",
              "bottoms", "45.00", "USD", "", "Indigo", "32", "12",
              "https://images.pexels.com/photos/1598507/pexels-photo-1598507.jpeg",
              "unisex", "جينز مستقيم الساق",
              "بنطال جينز بقصة مستقيمة وخصر متوسط، من قماش قطني متين بلون نيلي",
              "100% cotton denim", "Machine wash 30C inside out; wash with similar colours"]),
            (["Low-Top Canvas Sneaker", "CONFIT-SNEAKER-003",
              "Low-top canvas trainer with a vulcanised rubber sole",
              "footwear", "33.00", "USD", "", "Off-White", "42", "18",
              "https://images.pexels.com/photos/1598508/pexels-photo-1598508.jpeg",
              "unisex", "حذاء رياضي قماشي منخفض",
              "حذاء رياضي قماشي بنعل مطاطي مريح للاستخدام اليومي",
              "Cotton canvas, rubber sole", "Wipe clean with a damp cloth"]),
            (["Tailored Wool Blazer", "CONFIT-BLAZER-004",
              "Single-breasted blazer in Italian virgin wool",
              "outerwear", "128.00", "USD", "152.00", "Navy", "48", "8",
              "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg",
              "mens", "بليزر صوف مفصل",
              "بليزر صوف بقصة أحادية الصف وأزرار أمامية، مناسب للعمل والمناسبات",
              "100% virgin wool", "Dry clean only"]),
            (["Silk-Blend Maxi Dress", "CONFIT-DRESS-005",
              "Fluid silk-blend maxi dress with a draped bodice",
              "dresses", "97.00", "USD", "", "Crimson", "S", "6",
              "https://images.pexels.com/photos/1755428/pexels-photo-1755428.jpeg",
              "womens", "فستان ماكسي حريري",
              "فستان طويل من مزيج الحرير بلون قرمزي بقصة انسيابية",
              "Silk-viscose blend", "Hand wash cold; dry flat"]),
        ]
        for row in rows:
            writer.writerow(row)
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
                    # These are the slugs the seeded catalogue actually creates.
                    # The previous hint offered shirts/trousers/knitwear, none of
                    # which exist, so the "corrective action" walked the reader
                    # straight back into the same error.
                    suggestion = ("Use an existing category slug: "
                                  + ", ".join(BrandCatalogService.SEEDED_CATEGORY_SLUGS))
                elif field in ("stock_level", "stock_quantity"):
                    suggestion = "Enter an integer between 0 and 100000"
                elif field in ("thumbnail_url", "image_url"):
                    suggestion = ("Use a public HTTPS image URL from images.unsplash.com or "
                                  "images.pexels.com, or set image_source=own for your own photography")
                elif field == "image_source":
                    suggestion = "Leave blank for licensed stock photography, or set 'own' for your own images"
                elif field == "gender":
                    suggestion = "Use mens, womens or unisex"
                else:
                    suggestion = f"Verify {field} matches the required catalog format"
            writer.writerow([row_num, field, val, msg, suggestion])
        return output.getvalue()
