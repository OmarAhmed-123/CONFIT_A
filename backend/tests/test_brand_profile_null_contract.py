"""A brand must be able to open their own portal.

FOUND BY LIVE ROLE TESTING ON PRODUCTION, 2026-09-30
GET /brand/profile (and its /partner/profile alias) returned HTTP 500 for a
brand manager whose profile row carried NULLs in commission_rate,
return_rate_benchmark, current_return_rate or is_verified — the very first
call the B2B dashboard makes.

BrandProfileOut types those four as `int`/`bool`, NOT Optional, while the
model declared them with Python-side `default=` only: no nullable=False, no
server_default. A Python default fires on the ORM path and nowhere else, so
any import, backfill or SQL ops fix created a row the response model refused,
and FastAPI turned the ValidationError into a 500.

/brand/analytics kept returning 200 on the same row because it consumes the
profile internally and never serialises it — which is what made the failure
look endpoint-shaped rather than data-shaped.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect

from backend.app.models.user import BrandProfile
from backend.app.schemas.brand import BrandProfileOut

REQUIRED_NON_NULL = ("commission_rate", "return_rate_benchmark",
                     "current_return_rate", "is_verified")


@pytest.mark.parametrize("column", REQUIRED_NON_NULL)
def test_contract_required_columns_are_not_nullable(column):
    """The database must not be able to hold a row the API declares impossible."""
    col = inspect(BrandProfile).columns[column]
    assert col.nullable is False, (
        f"BrandProfileOut types {column} as non-Optional, so the column must be "
        "NOT NULL — otherwise a non-ORM writer produces a 500 on /brand/profile"
    )


@pytest.mark.parametrize("column", REQUIRED_NON_NULL)
def test_defaults_are_server_side_not_only_python_side(column):
    """A Python-side default only fires on the ORM path. Imports, backfills and
    ops fixes are not the ORM path."""
    col = inspect(BrandProfile).columns[column]
    assert col.server_default is not None, (
        f"{column} needs a server_default so every writer gets it, not just SQLAlchemy"
    )


def _rejects_none(annotation) -> bool:
    """True when the pydantic field cannot accept None.

    `Optional[str]` with no default is still *required* in pydantic v2, but it
    tolerates None — so `is_required()` alone is the wrong question. The
    combination that actually crashes is "required AND None not allowed".
    """
    import typing

    if annotation is None:
        return False
    if typing.get_origin(annotation) is typing.Union:
        return type(None) not in typing.get_args(annotation)
    return True


def test_schema_and_model_agree_on_nullability():
    """The invariant behind the defect: every response field that cannot
    accept None must be backed by a column the database guarantees."""
    columns = inspect(BrandProfile).columns
    offenders = []
    for name, field in BrandProfileOut.model_fields.items():
        if name not in columns:
            continue
        if _rejects_none(field.annotation) and columns[name].nullable:
            offenders.append(name)
    assert not offenders, (
        f"BrandProfileOut rejects None for {offenders}, but brand_profiles "
        "allows NULL there — a 500 waiting for any non-ORM writer"
    )
