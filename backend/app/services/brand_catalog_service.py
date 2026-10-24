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
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import and_ as sa_and, or_ as sa_or
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.app.core.money import validate_money
from backend.app.core.logging import logger
from backend.app.services import catalog_field_contract as field_contract
from backend.app.models.catalog import Product, ProductSKU, Category, StoreLocation, StoreInventory
from backend.app.models.user import BrandProfile, AuditLog
from backend.app.models.catalog_import import CatalogImportJob
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


class MediaOwnershipRefused(RuntimeError):
    """The brand is not authorized to fetch this image host (or a hop of it)."""


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

    #: How many rows between persisted progress updates (see import_products).
    _PROGRESS_EVERY = 10

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

        # Platform decisions a brand may never write (is_featured, is_active,
        # moderation, ratings). Checked FIRST and rejected, not stripped: a brand
        # that asked for featured placement must be told it is a CONFIT decision,
        # otherwise the request disappears and the column looks accepted.
        errors.extend(
            field_contract.forbidden_field_errors(
                row.keys(), row_number=row_num, error_factory=CatalogImportError,
            )
        )

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
                # A row priced in another currency is CONVERTED ONCE, here, at a
                # verified rate — or refused. It is never relabelled and never
                # guessed at.
                #
                # The rate is resolved during VALIDATION so the preview shows the
                # same verdict the import will act on: a brand must be able to
                # see "1,614.79 EGP → 31.00 USD at 52.09" before committing a
                # catalogue, not discover the conversion afterwards.
                try:
                    rate = self._catalog_rate(row['currency'])
                except Exception as exc:  # RateUnavailable and anything louder
                    reason = getattr(exc, 'reason', type(exc).__name__)
                    error('currency',
                          f'{row["currency"]} prices cannot be converted to {book} right now: {exc}',
                          f'Publish the row in {book}, or ask an operator to make a '
                          f'{row["currency"]} rate available ({reason})')
                    rate = None
                if rate is not None:
                    # Attached to the row so `import_products` applies the SAME
                    # rate the preview displayed. Re-resolving at write time
                    # would let the two disagree if the provider refreshed in
                    # between — and it is the write that becomes permanent.
                    row['_fx_rate'] = rate
                    self._validate_converted_prices(row, rate, error)


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
            self._validate_image_source(row, url, error, brand_id)

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
            if field == 'images':
                # Media URLs are data, not vocabulary: bounded and stored as given.
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
                continue

            # Style and occasion are MATCHED by other services: the catalogue
            # search filters on occasion text and the styling engine scores
            # occasion appropriateness. Storing a brand's free wording verbatim
            # ("office") published a product that no "Work & Business" filter
            # could ever return — imported, live, and unfindable. The importer
            # therefore writes the canonical vocabulary.
            kind = 'style' if field == 'style_tags' else 'occasion'
            try:
                raw_tags = field_contract.split_tag_cell(val)
            except ValueError as exc:
                error(field, f'Invalid tag list: {exc}', 'Use comma-separated tags')
                continue
            canonical, unrecognised = field_contract.canonical_tags(raw_tags, kind)
            row[field] = json.dumps(canonical, ensure_ascii=False)
            row[f'_{kind}_unrecognised'] = unrecognised

        for field in ('dominant_hex', 'color_hex'):
            if row.get(field) and (not isinstance(row[field], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', row[field])):
                error(field, 'Must be a six-digit hex color', 'Use #RRGGBB format like #1B1F3B')

        return errors

    #: mens | womens | unisex — the vocabulary `services/styling/garment_gender`
    #: filters on. Kept as a tuple here so a bad CSV value can be reported
    #: against the same list the stylist uses.
    VALID_GENDERS = ('mens', 'womens', 'unisex')

    def _catalog_rate(self, source_currency: str):
        """Resolve the verified SOURCE → price-book rate for this import.

        Cached per service instance: one API request may validate a thousand
        rows in the same currency, and re-asking the provider per row would
        make the provider's TTL irrelevant while producing a file whose rows
        could carry two different rates. One resolution, one rate, one
        provenance record for the whole import.
        """
        book = self._pricing_currency()
        cache = getattr(self, '_fx_cache', None)
        if cache is None:
            cache = {}
            self._fx_cache = cache
        key = ((source_currency or '').strip().upper(), book)
        if key not in cache:
            from backend.app.services.catalog_fx import resolve_rate
            cache[key] = resolve_rate(key[0], book)  # raises RateUnavailable
        return cache[key]

    def _validate_converted_prices(self, row, rate, error) -> None:
        """Refuse a conversion the price book cannot legally hold.

        ``catalog_fx`` answers "what is this worth in USD"; this answers "is the
        answer storable". A rate of 0.0001 on a 1,000,000 EGP row converts to a
        number NUMERIC(12,2) cannot represent, and discovering that at INSERT
        time would abort the row with a database error instead of a sentence the
        brand can act on.
        """
        from decimal import Decimal, InvalidOperation
        for field, amount_key in (('base_price', 'base_price'), ('compare_at_price', 'compare_at_price')):
            raw = row.get(amount_key)
            if raw in (None, ''):
                continue
            try:
                amount = Decimal(str(raw).strip())
            except (InvalidOperation, TypeError, ValueError):
                error(field, f'"{raw}" is not a decimal amount', 'Use a plain number such as 1450.00')
                continue
            if not amount.is_finite() or amount <= 0:
                # The base validator already refuses these; repeating the check
                # here keeps the conversion honest even if that rule changes.
                error(field, 'Price must be a positive number', 'Use a positive amount')
                continue
            try:
                converted = rate.convert(amount, field)
            except Exception as exc:  # RateUnavailable for an unusable amount
                error(field, f'Could not convert {amount} {row.get("currency")}: {exc}',
                      f'Check the price, or publish the row in {self._pricing_currency()}')
                continue
            if converted <= 0:
                # A rounding-down to zero would publish a free product. That is
                # a data problem, not a bargain.
                error(field,
                      f'{amount} {row.get("currency")} converts to {converted} '
                      f'{self._pricing_currency()}, which is not a sellable price '
                      f'at the current rate ({rate.describe()})',
                      'Use a larger amount, or publish the row in '
                      f'{self._pricing_currency()}')
            row.setdefault('_fx_preview', {})[field] = str(converted)

    def convert_row_prices(self, row) -> dict:
        """Apply the row's resolved rate to its amounts. Returns provenance.

        Used by ``import_products`` — i.e. only on the COMMIT path, never in
        preview. Preview reads ``row['_fx_preview']``, which was computed from
        the same ``CatalogRate`` object, so what the brand approved and what was
        written cannot diverge.
        """
        rate = row.get('_fx_rate')
        if rate is None:
            return {}
        for field in ('base_price', 'compare_at_price'):
            raw = row.get(field)
            if raw in (None, ''):
                continue
            from decimal import Decimal
            converted = rate.convert(Decimal(str(raw).strip()), field)
            row['_fx_original_' + field] = str(raw)
            row[field] = str(converted)
        provenance = rate.provenance()
        # The amount the brand actually supplied, kept verbatim.
        provenance['price_source_amount'] = row.get('_fx_original_base_price')
        return provenance

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

    def _validate_image_source(self, row, url, error, brand_id=None) -> None:
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

        # OWNERSHIP IS CHECKED FOR EVERY SOURCE, INCLUDING `own`.
        #
        # The flag `CATALOG_IMPORT_ALLOW_OWN_IMAGES` only says "this deployment
        # may fetch first-party URLs". It never said WHOSE URL, so with it on any
        # brand could point an import at a competitor's CDN and the platform
        # would copy that photography into its own catalogue under the wrong
        # brand. Authorization is now per-brand and server-side: the host must be
        # a claimed-and-verified domain of THIS brand (migration 0045).
        #
        # The declared `image_source` column is a hint, never an authorization:
        # a client-supplied string cannot grant itself permission.
        #
        # ORDER OF CHECKS. The deployment flag is asked FIRST because it is a
        # property of the SERVER, not of this URL: if first-party imports are
        # switched off here, no URL can succeed and telling the brand to verify a
        # domain would send them down a path that cannot work. Only then does
        # per-brand ownership matter.
        stock_sources = ', '.join(APPROVED_SOURCE_HOSTS)
        if declared == 'own' and not self._own_images_allowed():
            error('image_source',
                  'First-party image imports are disabled on this deployment, so an '
                  'image URL from your own domain cannot be imported yet',
                  'Upload product photography through the brand dashboard, or use a '
                  'licensed stock URL from ' + stock_sources)
            return

        if brand_id:
            from backend.app.services.image_ownership import ImageOwnershipService
            decision = ImageOwnershipService(self.db).authorize_url(brand_id, url)
            if not decision.allowed:
                # Both routes forward are named: use a licensed stock host, or
                # verify the domain. An error with one option is a dead end for
                # whichever brand the other option suited.
                error('thumbnail_url',
                      f'This image cannot be imported: {ImageOwnershipService.explain(decision)}',
                      f'Use a licensed stock URL from {stock_sources}, or verify your own '
                      f'domain in the brand settings (reason: {decision.reason})')
                return
            row['_image_ownership'] = decision.as_dict()
            effective_source = decision.source_type
        else:
            effective_source = 'stock' if declared != 'own' else 'own'

        if effective_source == 'own':
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
                  f'Use a licensed stock URL from {stock_sources}, or verify your own '
                  f'domain in the brand settings and set image_source=own')

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

        # Tags that do not belong to CONFIT's controlled occasion vocabulary are
        # stored (the brand's data is not deleted) but they will never match a
        # catalogue filter or the stylist. Saying so in the preview is the only
        # moment the brand can still fix it.
        for kind, field in (('occasion', 'occasion_tags'), ('style', 'style_tags')):
            unknown = row.get(f'_{kind}_unrecognised') or []
            if unknown:
                warn(field,
                     'These tags are not in CONFIT\'s '
                     f'{kind} vocabulary and will not match filters or the stylist: '
                     + ', '.join(unknown[:8])
                     + ('' if len(unknown) <= 8 else f' (+{len(unknown) - 8} more)'))

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

        # Two columns that resolve to the SAME field. The importer takes the first
        # non-empty value, which means the price a brand sees in the preview can
        # change if their next export orders the columns differently — a silent
        # difference between two imports of "the same" file.
        resolution = field_contract.resolve_headers(
            fields,
            aliases={**self.HEADER_ALIASES, **{f: f for f in self.REQUIRED_FIELDS + self.OPTIONAL_FIELDS}},
            known=list(self.REQUIRED_FIELDS) + list(self.OPTIONAL_FIELDS),
        )
        for canonical, headers in resolution['collisions']:
            out.append({
                'row': 1,
                'field': canonical,
                'message': (f'Columns {", ".join(repr(h) for h in headers)} all mean '
                            f'"{canonical}"; the first non-empty one is used. Keep only one '
                            f'to make imports reproducible.'),
            })
        for name, field, reason in resolution['forbidden']:
            out.append({
                'row': 1,
                'field': field,
                'message': (f'Column "{name}" cannot be set by a brand import: {reason}. '
                            f'It will be rejected, not applied.'),
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
                # `price` is what will be STORED. When the row was supplied in
                # another currency it is already the converted amount in the
                # price book denomination — a preview that showed the raw 1,614.79
                # beside a product that will be sold at 31.00 would be the same
                # two-prices-for-one-product defect this conversion exists to
                # remove.
                "price": (row.get('_fx_preview') or {}).get('base_price') or str(row.get('base_price')),
                "original_price": (
                    (row.get('_fx_preview') or {}).get('compare_at_price')
                    or (str(row.get('compare_at_price')) if row.get('compare_at_price') else None)
                ),
                "currency": self._pricing_currency(),
                # Provenance the brand can act on: the amounts as THEY supplied
                # them and the rate that moved them, so a surprising converted
                # price is explainable on the preview screen rather than after
                # the catalogue is live.
                "source_currency": row.get('currency') or self._pricing_currency(),
                "source_price": str(row.get('base_price')),
                "fx_rate": (str(row['_fx_rate'].provider_rate)
                            if row.get('_fx_rate') is not None else None),
                "fx_converted": bool(row.get('_fx_preview')),
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

    def import_products(self, valid_rows, brand_id, target_store_id=None, on_progress=None):
        """Persist normalised rows.

        ``on_progress(processed)`` is called as rows are handled, so a background
        job can persist real progress. It is called every `_PROGRESS_EVERY` rows
        rather than per row: a per-row commit would make progress cost more than
        the work it describes.
        """
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
            if on_progress is not None and fallback_number % self._PROGRESS_EVERY == 0:
                try:
                    on_progress(fallback_number)
                except Exception:  # progress must never break the import
                    logger.warning('catalog_import_progress_failed', row=number)
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
                # CONVERT BEFORE WRITING, EXACTLY ONCE.
                #
                # `row['_fx_rate']` was resolved during validation and is the
                # same object the preview displayed, so the amount the brand
                # approved is the amount stored. After this call every price on
                # the row is in the price book's denomination and `row['currency']`
                # is replaced by it — one number, one label, no second reading.
                #
                # A row already priced in the book currency returns {} and is
                # untouched: there is no path here that converts an amount that
                # was never in another currency, which is what makes double
                # conversion impossible rather than merely unlikely.
                fx_provenance = self.convert_row_prices(row)
                if fx_provenance:
                    row['currency'] = self._pricing_currency()
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
                if fx_provenance:
                    # Written on the row that was converted. A re-import of the
                    # same product at a different rate overwrites this — the
                    # provenance belongs to the CURRENT price, not to the first
                    # one — while `price_source_amount` keeps what the brand
                    # supplied in the file that produced this price.
                    for key, value in fx_provenance.items():
                        if value is not None:
                            setattr(product, key, value)
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
                    # A per-SKU override is an absolute price in the SAME
                    # denomination as the row. Left unconverted it would be a
                    # second, silently inconsistent price for the variant, so it
                    # follows the row's rate too.
                    override = row['price_override']
                    if row.get('_fx_rate') is not None:
                        from decimal import Decimal
                        override = str(row['_fx_rate'].convert(Decimal(str(override).strip()), 'price_override'))
                    sku.price_override = validate_money(override, 'price_override', allow_zero=False, required=True, exact_scale=True)
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
                media = self._materialize_media(product, row, brand_id=brand_id)
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

    def _ownership_gate(self, brand_id):
        """A per-hop authorizer for the fetch, or None when there is no brand.

        Returned as a closure so `safe_get` can apply it to the FIRST url and to
        every redirect destination. A failure raises `MediaOwnershipRefused`,
        which the caller records as a per-photograph reason rather than a
        traceback.
        """
        if not brand_id:
            return None

        from backend.app.services.image_ownership import ImageOwnershipService

        gate_service = ImageOwnershipService(self.db)

        def allow(url: str) -> None:
            decision = gate_service.authorize_url(brand_id, url)
            if not decision.allowed:
                raise MediaOwnershipRefused(
                    f"{decision.reason}: {gate_service.explain(decision)}"
                )

        return allow

    def _materialize_media(self, product, row, brand_id=None):
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
            # Re-checked at the point of use, not only at validation time: the
            # two run in different transactions (validation on preview, this in
            # the worker), and a domain revoked between them must stop the
            # import. Time-of-check/time-of-use is a real gap when the check and
            # the fetch are minutes apart.
            ownership_gate = self._ownership_gate(brand_id)
            _, failures = service.materialize_photos(
                product,
                photos,
                # The caller owns the transaction. If verification below fails,
                # the product, its SKUs and its media rows must all disappear
                # together — a committed-then-rejected row would be the worst
                # of both worlds: reported as rejected, yet live in the catalog.
                commit=False,
                ownership_gate=ownership_gate,
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

    def _notify_import_complete(self, actor_id, job) -> None:
        """Best-effort in-app notification to the brand member who ran a
        catalogue import. Guarded: logged and swallowed, never changes the
        import outcome. No-op without an actor (e.g. a system retry)."""
        if not actor_id:
            return
        try:
            from backend.app.services.notification_service import NotificationService

            label = {
                "completed": "completed",
                "partially_completed": "partially completed",
                "failed": "failed",
            }.get(job.status, job.status)
            NotificationService(self.db).create(
                actor_id,
                "catalog_import",
                f"Catalogue import {label}",
                body=(f"{job.accepted_rows} accepted, {job.rejected_rows} rejected "
                      f"of {job.total_rows} rows."),
                link="/brand-dashboard",
                data={
                    "job_id": job.id,
                    "status": job.status,
                    "accepted": job.accepted_rows,
                    "rejected": job.rejected_rows,
                    "total": job.total_rows,
                },
            )
        except Exception as exc:  # noqa: BLE001 — never fail the import on a notification
            from backend.app.core.logging import logger as _logger

            _logger.warning("import_notification_failed", job_id=getattr(job, "id", "?"), error=str(exc)[:200])

    def _process(self, brand_id, file_name, file_size, prepare, actor_id=None, target_store_id=None,
                 send_notifications=False, job=None):
        """Run an import against a job row and persist the outcome.

        ``job`` is the row a worker already claimed (or the one this call creates
        for the synchronous paths). It is deliberately a parameter: the
        background worker must write its result to the SAME row the API returned,
        otherwise the brand polls a job that never changes.
        """
        job = job or self.brand_repo.create_import_job(brand_id, file_name, file_size)
        job_id = job.id
        try:
            job.status, job.started_at = 'processing', datetime.now(timezone.utc)
            job.heartbeat_at = job.started_at
            self._photo_warnings = []
            self.db.commit()

            def _progress(processed):
                # Real progress, committed as it happens: a job that says
                # "processing" for four minutes is indistinguishable from a
                # stuck one without this.
                self.db.query(type(job)).filter(type(job).id == job_id).update(
                    {'processed_rows': processed, 'heartbeat_at': datetime.now(timezone.utc)},
                    synchronize_session=False,
                )
                self.db.commit()

            valid, validation_errors, stats = prepare()
            (accepted, rejected, import_errors, new_prods, missing_ar, media_rows,
             missing_desc_ar, gender_inferred) = self.import_products(
                valid, brand_id, target_store_id=target_store_id, on_progress=_progress)
            errors = [e.to_dict() for e in validation_errors] + import_errors
            job.total_rows, job.accepted_rows = stats['total'], accepted
            job.rejected_rows = stats['rejected'] + rejected
            job.duplicate_rows = stats['duplicate']
            job.status = 'completed' if accepted and not errors else 'partially_completed' if accepted else 'failed'
            job.errors_json, job.completed_at = json.dumps(errors), datetime.now(timezone.utc)
            job.processed_rows = stats['total']
            job.heartbeat_at = job.completed_at
            job.last_error = None
            # The catalogue itself is no longer needed: keeping 10 MB of CSV per
            # finished job is storage for nothing. It is kept on a FAILED job so
            # a retry can re-run the same bytes.
            job.payload_text = None
            self.db.add(AuditLog(user_id=actor_id, action='BRAND_CATALOG_IMPORTED', resource_type='CatalogImportJob',
                                 resource_id=str(job_id), details_json=json.dumps(dict(brand_id=brand_id, accepted=accepted, rejected=job.rejected_rows))))
            self.db.commit()

            # Best-effort in-app notification to the brand member who ran the
            # import (never changes the import's outcome).
            self._notify_import_complete(actor_id, job)

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
        except Exception as exc:
            self.db.rollback()
            job = self.brand_repo.get_import_job(job_id, brand_id)
            if job:
                job.status, job.completed_at = 'failed', datetime.now(timezone.utc)
                job.last_error = f'{type(exc).__name__}: {exc}'[:500]
                job.errors_json = json.dumps([CatalogImportError(0, 'system', 'Import interrupted; inspect catalog before retrying').to_dict()])
                # payload_text stays: a failed job is retryable with the same bytes.
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

    # ------------------------------------------------------------------
    # Durable background execution (migration 0042)
    # ------------------------------------------------------------------
    #: A job whose heartbeat is older than this is considered abandoned and may
    #: be re-claimed. Live worker tasks refresh the heartbeat as they process.
    JOB_LEASE_SECONDS = 900
    #: A worker may claim a job this many times in total. Beyond that the job is
    #: terminal-failed: an import that keeps crashing must not retry forever.
    MAX_JOB_ATTEMPTS = 3

    def enqueue_csv_import(self, csv_content, brand_id, file_name=None, actor_id=None,
                           target_store_id=None, send_notifications=False):
        """Create the durable job and NOT process it.

        Returns the job row. The caller dispatches it to the worker; if dispatch
        fails the caller must mark it (see ``mark_dispatch_failed``) rather than
        report a queued import that nothing will ever run.
        """
        job = self.brand_repo.create_import_job(brand_id, file_name, len(csv_content.encode()))
        job.payload_text = csv_content
        job.payload_sha256 = hashlib.sha256(csv_content.encode('utf-8')).hexdigest()
        job.target_store_id = target_store_id
        job.send_notifications = bool(send_notifications)
        job.actor_id = actor_id
        job.status = 'queued'
        job.processed_rows = 0
        job.attempts = 0
        self.db.commit()
        self.db.refresh(job)
        logger.info('catalog_import_enqueued', job_id=job.id, brand_id=brand_id,
                    bytes=job.file_size)
        return job

    def mark_dispatch_failed(self, job_id, reason):
        """The queue rejected the job: say so, and leave it recoverable.

        A job row that stays ``queued`` after a failed dispatch is the exact
        "we accepted your import" lie this whole path exists to remove. It goes
        to ``failed`` with the reason recorded; the payload is kept, so the
        operator (or the recovery sweep) can re-dispatch the same bytes.
        """
        job = self.db.query(CatalogImportJob).filter(CatalogImportJob.id == job_id).first()
        if not job:
            return None
        job.status = 'failed'
        job.last_error = f'dispatch_failed: {reason}'[:500]
        job.errors_json = json.dumps([CatalogImportError(
            0, 'system',
            'The import queue is unavailable, so this file was not imported. Nothing was changed.',
        ).to_dict()])
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        logger.error('catalog_import_dispatch_failed', job_id=job_id, reason=str(reason)[:200])
        return job

    def claim_job(self, job_id):
        """Atomically take ownership of a queued job. Returns (job, claimed).

        The conditional UPDATE is the concurrency control: two workers (or a
        worker and a retry click) race here, and exactly one wins. A job that is
        already terminal returns ``claimed=False`` so a redelivered message is a
        no-op instead of a second import — which is what stops duplicate
        products.
        """
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=self.JOB_LEASE_SECONDS)
        open_states = ('queued', 'failed')
        claimed_rows = (
            self.db.query(CatalogImportJob)
            .filter(CatalogImportJob.id == job_id)
            .filter(CatalogImportJob.attempts < self.MAX_JOB_ATTEMPTS)
            .filter(
                sa_or(
                    CatalogImportJob.status.in_(open_states),
                    sa_and(CatalogImportJob.status == 'processing',
                           sa_or(CatalogImportJob.heartbeat_at.is_(None),
                                 CatalogImportJob.heartbeat_at < stale_before)),
                )
            )
            .update(
                {
                    'status': 'processing',
                    'started_at': now,
                    'heartbeat_at': now,
                    'attempts': CatalogImportJob.attempts + 1,
                    'last_error': None,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        job = self.db.query(CatalogImportJob).filter(CatalogImportJob.id == job_id).first()
        if job is None:
            raise ValueError(f'import job {job_id} does not exist')
        if not claimed_rows:
            if job.attempts >= self.MAX_JOB_ATTEMPTS and job.status != 'completed':
                job.status = 'failed'
                job.last_error = (job.last_error or '')[:400] or 'retry limit reached'
                job.completed_at = now
                self.db.commit()
            return job, False
        return job, True

    def execute_import_job(self, job_id):
        """Run a claimed job from its stored payload. Idempotent by construction.

        A terminal job returns its stored result untouched — re-delivering the
        task cannot import the catalogue twice.
        """
        job, claimed = self.claim_job(job_id)
        if not claimed:
            logger.info('catalog_import_job_not_claimed', job_id=job_id, status=job.status,
                        attempts=job.attempts)
            return self.job_result(job)
        if not job.payload_text:
            job.status = 'failed'
            job.last_error = 'payload_missing'
            job.errors_json = json.dumps([CatalogImportError(
                0, 'system',
                'The uploaded file is no longer available for this job; upload it again.',
            ).to_dict()])
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return self.job_result(job)

        return self._process(
            job.brand_id,
            job.file_name,
            job.file_size,
            lambda: self.parse_csv(job.payload_text, job.brand_id,
                                   target_store_id=job.target_store_id),
            actor_id=job.actor_id,
            target_store_id=job.target_store_id,
            send_notifications=bool(job.send_notifications),
            job=job,
        )

    def job_result(self, job):
        """The API/stored shape of a job row (same keys the sync path returns)."""
        try:
            errors = json.loads(job.errors_json or '[]')
        except (TypeError, ValueError):
            errors = []
        return dict(
            job_id=job.id,
            status=job.status,
            total_rows=job.total_rows,
            processed_rows=job.processed_rows or 0,
            accepted_rows=job.accepted_rows,
            rejected_rows=job.rejected_rows,
            duplicate_rows=job.duplicate_rows,
            errors=errors[:50],
            last_error=job.last_error,
            attempts=job.attempts or 0,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    def recover_open_jobs(self, limit=25):
        """Re-dispatch jobs that are open but nobody is working on.

        Two real situations produce these: the API committed the job and the
        broker was unreachable at dispatch time (status ``queued``), and a worker
        was killed mid-import (status ``processing`` with a stale heartbeat).
        Returns the job ids that were handed back to the queue.
        """
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=self.JOB_LEASE_SECONDS)
        jobs = (
            self.db.query(CatalogImportJob)
            .filter(CatalogImportJob.payload_text.isnot(None))
            .filter(CatalogImportJob.attempts < self.MAX_JOB_ATTEMPTS)
            .filter(
                sa_or(
                    CatalogImportJob.status == 'queued',
                    sa_and(CatalogImportJob.status == 'processing',
                           sa_or(CatalogImportJob.heartbeat_at.is_(None),
                                 CatalogImportJob.heartbeat_at < stale_before)),
                )
            )
            .order_by(CatalogImportJob.created_at.asc())
            .limit(limit)
            .all()
        )
        return [j.id for j in jobs]

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
            writer.writerow([
                BrandCatalogService._csv_safe_cell(row_num),
                BrandCatalogService._csv_safe_cell(field),
                BrandCatalogService._csv_safe_cell(val),
                BrandCatalogService._csv_safe_cell(msg),
                BrandCatalogService._csv_safe_cell(suggestion),
            ])
        return "\ufeff" + output.getvalue()

    @staticmethod
    def _csv_safe_cell(value: Any) -> Any:
        """Neutralize spreadsheet formula triggers (=, +, -, @, tab, CR) on CSV export."""
        if value is None or isinstance(value, (int, float, bool)):
            return value
        text = str(value)
        stripped = text.lstrip(" ")
        if stripped and stripped[0] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + text
        if text[:1] in ("\t", "\r"):
            return "'" + text
        return text

    def export_catalog_csv(self, brand_id: int) -> str:
        """Export strictly the caller's brand catalog + SKUs as UTF-8 BOM CSV with formula neutralization."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "product_id",
            "slug",
            "title",
            "title_ar",
            "category_slug",
            "gender",
            "currency",
            "base_price",
            "compare_at_price",
            "sku_code",
            "size",
            "color",
            "price_override",
            "stock_level",
            "is_in_stock",
        ])
        products = self.brand_repo.get_brand_products(brand_id)
        for p in products:
            cat_slug = p.category.slug if p.category else ""
            skus = list(p.skus or [])
            if not skus:
                writer.writerow([
                    p.id,
                    self._csv_safe_cell(p.slug),
                    self._csv_safe_cell(p.title),
                    self._csv_safe_cell(p.title_ar or ""),
                    self._csv_safe_cell(cat_slug),
                    self._csv_safe_cell(p.gender or "unisex"),
                    self._csv_safe_cell(p.currency or "USD"),
                    str(p.base_price),
                    str(p.compare_at_price) if p.compare_at_price is not None else "",
                    "",
                    "",
                    self._csv_safe_cell(p.color_family or ""),
                    "",
                    0,
                    False,
                ])
            else:
                for sku in skus:
                    writer.writerow([
                        p.id,
                        self._csv_safe_cell(p.slug),
                        self._csv_safe_cell(p.title),
                        self._csv_safe_cell(p.title_ar or ""),
                        self._csv_safe_cell(cat_slug),
                        self._csv_safe_cell(p.gender or "unisex"),
                        self._csv_safe_cell(p.currency or "USD"),
                        str(p.base_price),
                        str(p.compare_at_price) if p.compare_at_price is not None else "",
                        self._csv_safe_cell(sku.sku_code),
                        self._csv_safe_cell(sku.size),
                        self._csv_safe_cell(sku.color),
                        str(sku.price_override) if sku.price_override is not None else "",
                        int(sku.stock_level or 0),
                        bool(sku.is_in_stock),
                    ])
        return "\ufeff" + output.getvalue()
