"""Tests for the service-layer identity rename.

Renaming a live brand is the kind of operation that quietly breaks a link or
crosses a tenant boundary when it is done as an ad-hoc UPDATE. These tests pin
the guards: strict validation, slug uniqueness, and tenant isolation on stores.

Every test uses its own generated names, so the suite is repeatable against a
seed database that already contains the house brands.
"""
import uuid

import pytest

from backend.app.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationDomainError
from backend.app.core.security import get_password_hash
from backend.app.models.catalog import StoreLocation
from backend.app.models.user import BrandProfile, User
from backend.app.services.brand_service import BrandService


@pytest.fixture()
def db_session():
    from backend.tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture(autouse=True)
def _cleanup_identities(db_session):
    """Remove only the rows these tests created, identified by their probe user."""
    yield
    db_session.rollback()
    probes = db_session.query(User).filter(User.email.like("rename-probe-%")).all()
    for user in probes:
        for brand in db_session.query(BrandProfile).filter(BrandProfile.user_id == user.id).all():
            db_session.query(StoreLocation).filter(StoreLocation.brand_id == brand.id).delete()
            db_session.delete(brand)
        db_session.delete(user)
    db_session.commit()


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _brand(db, name, slug):
    user = User(email=f"rename-probe-{slug}@example.test", hashed_password=get_password_hash("x"),
                full_name="Rename Probe", role="brand")
    db.add(user)
    db.commit()
    db.refresh(user)
    brand = BrandProfile(user_id=user.id, brand_name=name, slug=slug)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def test_rename_changes_name_and_slug_together(db_session):
    t = _tag()
    brand = _brand(db_session, f"Imitation Probe {t}", f"probe-{t}")
    result = BrandService(db_session).rename_brand(brand.id, f"Casa Probe {t}")

    assert result["before"] == {"brand_name": f"Imitation Probe {t}", "slug": f"probe-{t}"}
    assert result["after"] == {"brand_name": f"Casa Probe {t}", "slug": f"casa-probe-{t}"}
    db_session.refresh(brand)
    assert (brand.brand_name, brand.slug) == (f"Casa Probe {t}", f"casa-probe-{t}")


def test_rename_refuses_a_slug_owned_by_another_brand(db_session):
    t = _tag()
    taken = _brand(db_session, f"Taken Probe {t}", f"taken-{t}")
    other = _brand(db_session, f"Other Probe {t}", f"other-{t}")

    with pytest.raises(ValidationDomainError):
        BrandService(db_session).rename_brand(other.id, f"Renamed {t}", slug=taken.slug)


def test_rename_allows_a_brand_to_keep_its_own_slug(db_session):
    t = _tag()
    brand = _brand(db_session, f"Keep Probe {t}", f"keep-{t}")
    result = BrandService(db_session).rename_brand(brand.id, f"Kept Probe {t}", slug=f"keep-{t}")
    assert result["after"] == {"brand_name": f"Kept Probe {t}", "slug": f"keep-{t}"}


@pytest.mark.parametrize("bad", ["", " ", "A", None])
def test_rename_rejects_a_degenerate_name(db_session, bad):
    t = _tag()
    brand = _brand(db_session, f"Degenerate Probe {t}", f"degenerate-{t}")
    with pytest.raises(ValidationDomainError):
        BrandService(db_session).rename_brand(brand.id, bad)


def test_rename_rejects_an_over_long_name(db_session):
    t = _tag()
    brand = _brand(db_session, f"Long Probe {t}", f"long-{t}")
    with pytest.raises(ValidationDomainError):
        BrandService(db_session).rename_brand(brand.id, "x" * 121)


def test_rename_of_a_missing_brand_is_not_found(db_session):
    with pytest.raises(ResourceNotFoundError):
        BrandService(db_session).rename_brand(999_999, "Nordhaus")


def test_store_rename_keeps_the_location_suffix(db_session):
    t = _tag()
    brand = _brand(db_session, f"Store Probe {t}", f"store-{t}")
    store = StoreLocation(brand_id=brand.id, name=f"Brand — Mall {t}", name_ar="فرع",
                          address="Address", city="Cairo", country="EG",
                          latitude=30.0444, longitude=31.2357)
    db_session.add(store)
    db_session.commit()

    result = BrandService(db_session).rename_store(store.id, brand.id, f"House — Mall {t}")
    assert result["before"] == f"Brand — Mall {t}"
    assert result["after"] == f"House — Mall {t}"
    db_session.refresh(store)
    assert store.name == f"House — Mall {t}"


def test_store_rename_refuses_cross_tenant_mutation(db_session):
    t = _tag()
    owner = _brand(db_session, f"Owner Probe {t}", f"owner-{t}")
    intruder = _brand(db_session, f"Intruder Probe {t}", f"intruder-{t}")
    store = StoreLocation(brand_id=owner.id, name=f"Owner — Mall {t}", name_ar="فرع",
                          address="Address", city="Cairo", country="EG",
                          latitude=30.0444, longitude=31.2357)
    db_session.add(store)
    db_session.commit()

    with pytest.raises(AuthorizationError):
        BrandService(db_session).rename_store(store.id, intruder.id, "Hijacked Store")
    db_session.refresh(store)
    assert store.name == f"Owner — Mall {t}", "a refused rename must change nothing"
