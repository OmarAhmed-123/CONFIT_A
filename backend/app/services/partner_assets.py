"""Private object storage with same-origin, publication-aware image delivery.

A durable upload intent precedes the object write; interrupted uploads remain
collectable. No external URL is fetched by this service (no SSRF proxy).
"""
import hashlib
import io
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from backend.app.core.config import settings
from backend.app.models.brand_operations import ProductAsset
from backend.app.models.catalog import Product
from backend.app.services.brand_access import resolve
from backend.app.repositories.partner_catalog_repository import PartnerCatalogRepository
from backend.app.services.partner_audit import append_event
from backend.app.services.storage_service import S3StorageBackend, LocalStorageBackend

MAX_UPLOAD = 4 * 1024 * 1024
FORMATS = {'JPEG': ('image/jpeg', {'.jpg','.jpeg'}), 'PNG': ('image/png', {'.png'}), 'WEBP': ('image/webp', {'.webp'})}


def storage():
    if settings.BRAND_ASSET_PROVIDER == 's3':
        return S3StorageBackend(settings.model_copy(update={'AWS_S3_BUCKET': settings.BRAND_ASSET_BUCKET,
            'S3_PUBLIC_URL_BASE': None}))
    if settings.is_production:
        raise HTTPException(503, 'Persistent brand image storage is not configured')
    Path(settings.STORAGE_LOCAL_DIR).mkdir(parents=True, exist_ok=True)
    return LocalStorageBackend()


def normalize(data, filename, content_type):
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, 'Image must be at most 4 MiB')
    try:
        with Image.open(io.BytesIO(data)) as image:
            expected = FORMATS.get(image.format)
            if not expected or content_type != expected[0] or Path(filename or '').suffix.lower() not in expected[1]:
                raise ValueError('Image type mismatch')
            if image.width * image.height > 20_000_000 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Image dimensions or animation unsupported')
            image.load()
            clean = image.convert('RGB')
            clean.thumbnail((1600,1600))
            output = io.BytesIO()
            # Re-encoding strips EXIF and non-pixel content; SVG is never accepted.
            clean.save(output, format='WEBP', quality=85)
            value = output.getvalue()
            if len(value) > 2 * 1024 * 1024:raise ValueError('Optimized image too large')
            return value
    except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, 'Upload a valid non-animated JPEG, PNG or WebP image')


class PartnerAssetService:
    def __init__(self, db, user):
        self.db, self.user = db, user

    def upload(self, product_id, data, filename, content_type):
        data = normalize(data, filename, content_type)
        member = resolve(self.db, self.user, 'catalog.write', lock=True)
        product = PartnerCatalogRepository(self.db, member.brand_id).product(product_id, lock=True)
        backend = storage()
        prefix = settings.BRAND_ASSET_PREFIX
        if not re.fullmatch(r'[a-zA-Z0-9_/-]{1,100}', prefix) or '..' in prefix:
            raise HTTPException(503, 'Invalid brand storage namespace')
        asset_id = str(uuid4())
        key = f'{prefix}/{member.brand_id}/{asset_id}.webp'
        asset = ProductAsset(id=asset_id, brand_id=member.brand_id, product_id=product.id,
            object_key=key, sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data), state='upload_pending')
        self.db.add(asset)
        append_event(self.db, member.brand_id, 'BRAND_ASSET_UPLOAD_STARTED', 'ProductAsset', asset.id,
                     after={'sha256':asset.sha256,'byte_size':asset.byte_size})
        self.db.commit()  # durable intent, not product publication
        try:
            backend.store(key, data)
            # Permissions may have been revoked while the external write ran.
            resolve(self.db, self.user, 'catalog.write', lock=True)
            product = PartnerCatalogRepository(self.db, member.brand_id).product(product_id, lock=True)
            product.thumbnail_url = '/api/v1/catalog/assets/' + asset.id
            asset.state = 'active'
            append_event(self.db, member.brand_id, 'BRAND_ASSET_ATTACHED', 'Product', product.id, after={'asset_id':asset.id})
            self.db.commit()
        except Exception:
            self.db.rollback()
            # Durable intent is left for retryable garbage collection. Do not
            # convert storage/audit failure into an attached-image success.
            raise
        return {'id':asset.id,'url':product.thumbnail_url,'byte_size':asset.byte_size,'sha256':asset.sha256}

    def delete(self, asset_id):
        member = resolve(self.db, self.user, 'catalog.write', lock=True)
        asset = self.db.query(ProductAsset).filter_by(id=asset_id,brand_id=member.brand_id).with_for_update().first()
        if not asset:raise HTTPException(404,'Image unavailable')
        if asset.state == 'deleted':return {'state':'deleted'}
        product = PartnerCatalogRepository(self.db, member.brand_id).product(asset.product_id,lock=True)
        if product.thumbnail_url == '/api/v1/catalog/assets/' + asset.id:
            if product.is_active:raise HTTPException(409,'Unpublish or replace the cover image before deleting it')
            product.thumbnail_url = ''
        asset.state = 'delete_pending'
        append_event(self.db, member.brand_id, 'BRAND_ASSET_DELETION_REQUESTED', 'ProductAsset', asset.id)
        self.db.commit()
        purge(self.db, asset.id)
        return {'state':self.db.get(ProductAsset, asset.id).state}


def purge(db, asset_id):
    asset = db.query(ProductAsset).filter_by(id=asset_id).with_for_update().first()
    if not asset or asset.state not in ('upload_pending','delete_pending'):return False
    created = asset.created_at.replace(tzinfo=timezone.utc) if asset.created_at.tzinfo is None else asset.created_at
    if asset.state == 'upload_pending' and created > datetime.now(timezone.utc)-timedelta(hours=1):return False
    backend = storage()
    ok = backend.delete(asset.object_key)
    if not ok and isinstance(backend,LocalStorageBackend):ok = not backend.exists(asset.object_key)
    if not ok:return False
    asset.state = 'deleted'
    append_event(db,asset.brand_id,'BRAND_ASSET_PURGED','ProductAsset',asset.id)
    db.commit()
    return True


def read(db, asset_id, user=None):
    asset = db.query(ProductAsset).filter_by(id=asset_id,state='active').first()
    if not asset:raise HTTPException(404,'Image unavailable')
    product = db.get(Product,asset.product_id)
    if not product.is_active:
        if not user:raise HTTPException(404,'Image unavailable')
        if resolve(db,user).brand_id != asset.brand_id:raise HTTPException(404,'Image unavailable')
    data = storage().read(asset.object_key)
    if data is None:raise HTTPException(503,'Image storage unavailable')
    if len(data) != asset.byte_size or hashlib.sha256(data).hexdigest() != asset.sha256:
        raise HTTPException(503,'Image integrity check failed')
    return data
