"""Reversible look deletion — Undo for /builder and /my-looks.

Migration 0030 covered the wardrobe. The Undo spec also names "Remove look"
and "clear slot", and that half was still a hard delete:

    StylistRepository.delete_outfit:
        self.db.delete(outfit)   # OutfitItem rows cascade (all, delete-orphan)

So "Remove look" destroyed the outfit AND every line in it — nothing to undo.

THE PRIVACY CASE THE WARDROBE DID NOT HAVE
Outfits can be shared: `share_token` powers a public, unauthenticated page.
A naive soft delete would leave a "deleted" look reachable by anyone holding
the link. Deleting must revoke visibility immediately; restoring must bring
it back. Both are asserted below, because that is exactly the guarantee that
regresses silently.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models.stylist import Outfit
from backend.app.repositories.stylist_repository import StylistRepository
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def db():
    s = TestingSessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def repo(db):
    return StylistRepository(db)


@pytest.fixture
def outfit(db):
    row = Outfit(
        user_id=920_001, title="QA Look", occasion="Casual",
        total_price=0, compatibility_score=90,
        color_palette="[]", style_tags="[]",
        share_token=f"qa-token-{datetime.now(timezone.utc).timestamp()}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    yield row
    db.query(Outfit).filter(Outfit.user_id == 920_001).delete()
    db.commit()


# ── reversibility ────────────────────────────────────────────────────────────

def test_soft_delete_keeps_the_row(repo, outfit, db):
    repo.soft_delete_outfit(outfit.id)
    db.refresh(outfit)
    assert outfit.deleted_at is not None
    assert db.query(Outfit).filter(Outfit.id == outfit.id).first() is not None


def test_binned_look_disappears_from_my_looks(repo, outfit):
    assert outfit.id in {o.id for o in repo.get_user_outfits(920_001)}
    repo.soft_delete_outfit(outfit.id)
    assert outfit.id not in {o.id for o in repo.get_user_outfits(920_001)}


def test_binned_look_is_not_readable_by_id(repo, outfit):
    repo.soft_delete_outfit(outfit.id)
    assert repo.get_outfit_by_id(outfit.id) is None


def test_restore_brings_the_look_back_once(repo, outfit):
    repo.soft_delete_outfit(outfit.id)
    binned = repo.get_binned_outfit(outfit.id, 920_001)
    assert binned is not None
    repo.restore_outfit(binned)
    ids = [o.id for o in repo.get_user_outfits(920_001)]
    assert ids.count(outfit.id) == 1, "no duplicates after restore"


def test_outfit_items_survive_the_bin(repo, outfit, db):
    """The hard delete cascaded OutfitItem rows. Soft delete must not."""
    before = db.query(Outfit).filter(Outfit.id == outfit.id).first()
    item_count = len(before.items)
    repo.soft_delete_outfit(outfit.id)
    db.refresh(before)
    assert len(before.items) == item_count


# ── the privacy guarantee ────────────────────────────────────────────────────

def test_deleting_a_look_revokes_its_public_share_link(repo, outfit):
    """THE POINT: a 'deleted' look must not stay on the internet."""
    token = outfit.share_token
    assert repo.get_outfit_by_share_token(token) is not None

    repo.soft_delete_outfit(outfit.id)

    assert repo.get_outfit_by_share_token(token) is None, (
        "a binned look must not resolve through its public share token"
    )


def test_restoring_a_look_brings_its_share_link_back(repo, outfit):
    token = outfit.share_token
    repo.soft_delete_outfit(outfit.id)
    repo.restore_outfit(repo.get_binned_outfit(outfit.id, 920_001))
    assert repo.get_outfit_by_share_token(token) is not None


# ── failure modes ────────────────────────────────────────────────────────────

def test_soft_deleting_twice_is_a_no_op_not_a_crash(repo, outfit):
    assert repo.soft_delete_outfit(outfit.id) is not None
    assert repo.soft_delete_outfit(outfit.id) is None  # already binned


def test_another_user_cannot_reach_your_binned_look(repo, outfit):
    repo.soft_delete_outfit(outfit.id)
    assert repo.get_binned_outfit(outfit.id, 920_002) is None


def test_permanent_delete_still_removes_everything(repo, outfit, db):
    assert repo.delete_outfit(outfit.id) is True
    assert db.query(Outfit).filter(Outfit.id == outfit.id).first() is None


def test_permanent_delete_works_on_a_binned_look(repo, outfit, db):
    """Empty-the-bin must not require restoring first."""
    repo.soft_delete_outfit(outfit.id)
    assert repo.delete_outfit(outfit.id) is True
    assert db.query(Outfit).filter(Outfit.id == outfit.id).first() is None


def test_the_two_surfaces_share_one_retention_window(repo):
    """Wardrobe and outfits must not drift into different 'undo lasts N days'
    promises — the user sees one product."""
    from backend.app.controllers.outfit_controller import OUTFIT_BIN_RETENTION
    from backend.app.services.wardrobe_service import WardrobeService

    assert OUTFIT_BIN_RETENTION == WardrobeService.BIN_RETENTION
    assert isinstance(OUTFIT_BIN_RETENTION, timedelta)
