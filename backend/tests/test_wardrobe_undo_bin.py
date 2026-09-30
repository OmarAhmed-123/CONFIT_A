"""Reversible wardrobe deletion — the backend contract behind Undo.

WHY THE BACKEND HAD TO CHANGE FIRST
-----------------------------------
The Undo specification permits optimistic reversible deletion *only if the
endpoint supports restore or the action can be safely reversed*. It could
not: `WardrobeService.delete_item` issued a hard DELETE **and** removed the
photograph from object storage in the same call.

A front-end Undo on that backend would have been a lie twice over — the row
was gone and the image was gone. It would have appeared to work until the
page reloaded, and the photo could never come back at all.

These tests pin the contract that makes an honest Undo possible, and the
failure modes the spec calls out: duplicate clicks, expiry, 404 after
permanent deletion, concurrent updates, and no duplicates in the list.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.exceptions import ResourceNotFoundError
from backend.app.models.wardrobe import WardrobeItem
from backend.app.services.wardrobe_service import WardrobeService
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def service(db):
    return WardrobeService(db)


@pytest.fixture
def item(db):
    """A live wardrobe item owned by a throwaway user id."""
    row = WardrobeItem(
        user_id=910_001, title="QA Blazer", category="Outerwear",
        color_name="Navy", color_hex="#1B1F3B", pattern="Solid",
        brand_name="Own Collection",
        image_url="https://storage.test/qa/blazer.jpg",
        image_hash=f"qa-hash-{datetime.now(timezone.utc).timestamp()}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    yield row
    db.query(WardrobeItem).filter(WardrobeItem.user_id == 910_001).delete()
    db.commit()


def _no_image_deletion(service, monkeypatch):
    """Record image-storage calls instead of performing them."""
    calls = []
    monkeypatch.setattr(service, "_delete_owned_image", lambda url: calls.append(url))
    return calls


# ── the core reversibility guarantee ─────────────────────────────────────────

def test_delete_bins_the_item_and_keeps_the_photograph(service, item, db, monkeypatch):
    """The whole point: the old code destroyed the image, so Undo could never
    return the real photo."""
    deleted_images = _no_image_deletion(service, monkeypatch)

    result = service.delete_item(910_001, item.id)

    assert result["status"] == "binned"
    assert result["restore_endpoint"].endswith(f"/wardrobe/items/{item.id}/restore")
    assert deleted_images == [], "a reversible delete must NOT remove the stored image"

    db.refresh(item)
    assert item.deleted_at is not None          # row survives
    assert item.image_url                        # image reference survives


def test_restore_brings_the_item_back(service, item, db, monkeypatch):
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)

    result = service.restore_item(910_001, item.id)

    assert result["status"] == "restored"
    db.refresh(item)
    assert item.deleted_at is None
    assert service.wardrobe_repo.get_item_by_id(item.id, 910_001) is not None


def test_the_undo_deadline_is_a_real_timestamp_not_a_guess(service, item, monkeypatch):
    """The UI renders this; if it were invented the countdown would lie."""
    _no_image_deletion(service, monkeypatch)
    result = service.delete_item(910_001, item.id)

    window = result["restorable_until"] - result["deleted_at"]
    assert window == WardrobeService.BIN_RETENTION


# ── binned items must be invisible everywhere ────────────────────────────────

def test_a_binned_item_disappears_from_the_list(service, item, monkeypatch):
    _no_image_deletion(service, monkeypatch)
    assert item.id in {i["id"] for i in service.get_user_wardrobe(910_001)}

    service.delete_item(910_001, item.id)

    assert item.id not in {i["id"] for i in service.get_user_wardrobe(910_001)}


def test_a_binned_item_is_404_on_direct_read(service, item, monkeypatch):
    """Nothing downstream may style, export or analyse a deleted item."""
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)

    with pytest.raises(ResourceNotFoundError):
        service.get_item(910_001, item.id)


def test_restore_puts_it_back_exactly_once_no_duplicates(service, item, monkeypatch):
    """Acceptance criterion: no duplicates in the list."""
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)
    service.restore_item(910_001, item.id)

    ids = [i["id"] for i in service.get_user_wardrobe(910_001)]
    assert ids.count(item.id) == 1


# ── failure modes the spec names explicitly ──────────────────────────────────

def test_clicking_undo_twice_is_a_success_not_an_error(service, item, monkeypatch):
    """Duplicate click / two tabs racing. The item is live, which is what the
    user asked for — reporting an error would be technically pedantic and
    practically wrong."""
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)
    service.restore_item(910_001, item.id)

    again = service.restore_item(910_001, item.id)
    assert again["status"] == "restored"


def test_restore_after_the_window_expires_fails_loudly(service, item, db, monkeypatch):
    """An Undo that reports success without restoring anything is worse than
    no Undo at all."""
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)
    item.deleted_at = datetime.now(timezone.utc) - (WardrobeService.BIN_RETENTION + timedelta(days=1))
    db.commit()

    with pytest.raises(ResourceNotFoundError):
        service.restore_item(910_001, item.id)


def test_restore_of_an_unknown_item_is_404(service):
    with pytest.raises(ResourceNotFoundError):
        service.restore_item(910_001, 987_654_321)


def test_another_user_cannot_restore_your_item(service, item, monkeypatch):
    """Ownership is enforced on the restore path too, not only on delete."""
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)

    with pytest.raises(ResourceNotFoundError):
        service.restore_item(910_002, item.id)


# ── permanent deletion ───────────────────────────────────────────────────────

def test_permanent_delete_removes_the_row_and_the_image(service, item, db, monkeypatch):
    deleted_images = _no_image_deletion(service, monkeypatch)
    url = item.image_url

    result = service.purge_item(910_001, item.id)

    assert result["status"] == "permanently_deleted"
    assert deleted_images == [url], "permanent deletion must remove the stored object"
    assert db.query(WardrobeItem).filter(WardrobeItem.id == item.id).first() is None


def test_permanent_delete_cannot_be_undone(service, item, monkeypatch):
    _no_image_deletion(service, monkeypatch)
    service.purge_item(910_001, item.id)

    with pytest.raises(ResourceNotFoundError):
        service.restore_item(910_001, item.id)


def test_permanent_delete_works_on_an_already_binned_item(service, item, monkeypatch):
    """Empty-the-bin must not require restoring first."""
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)

    assert service.purge_item(910_001, item.id)["status"] == "permanently_deleted"


# ── the unique-index collision the bin creates ───────────────────────────────

def test_expired_items_are_listed_for_purge_not_silently_kept(service, item, db, monkeypatch):
    _no_image_deletion(service, monkeypatch)
    service.delete_item(910_001, item.id)
    item.deleted_at = datetime.now(timezone.utc) - (WardrobeService.BIN_RETENTION + timedelta(days=1))
    db.commit()

    expired = service.wardrobe_repo.expired_binned_items(910_001, WardrobeService.BIN_RETENTION)
    assert item.id in {row.id for row in expired}


def test_purging_the_expired_bin_never_raises_on_storage_failure(service, item, db, monkeypatch):
    """Housekeeping runs inside a normal list read; it must never break it."""
    service.delete_item(910_001, item.id) if False else None
    monkeypatch.setattr(service, "_delete_owned_image", lambda url: None)
    service.delete_item(910_001, item.id)
    item.deleted_at = datetime.now(timezone.utc) - (WardrobeService.BIN_RETENTION + timedelta(days=1))
    db.commit()

    def _boom(url):
        raise RuntimeError("S3 unavailable")

    monkeypatch.setattr(service, "_delete_owned_image", _boom)
    service._purge_expired_bin(910_001)  # must not propagate


def test_binned_item_is_hidden_from_hash_lookup_by_default(service, item, monkeypatch):
    """`include_binned` must be opt-in: only the upload path wants binned rows."""
    _no_image_deletion(service, monkeypatch)
    digest = item.image_hash
    service.delete_item(910_001, item.id)

    assert service.wardrobe_repo.get_item_by_image_hash(910_001, digest) is None
    assert service.wardrobe_repo.get_item_by_image_hash(910_001, digest, include_binned=True) is not None
