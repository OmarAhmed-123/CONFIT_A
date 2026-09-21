"""Existing-data rehearsal on the real migration chain (scratch DB only)."""
from datetime import datetime
from sqlalchemy import MetaData, Table, select
from backend.tests.test_schema_drift_gate import scratch_db, _alembic


def test_backfill_preserves_existing_founders_and_rolling_insert(scratch_db):
    url, engine = scratch_db
    _alembic(url, 'up', '0018_outfit_share_lifecycle')
    metadata = MetaData()
    users = Table('users', metadata, autoload_with=engine)
    brands = Table('brand_profiles', metadata, autoload_with=engine)
    created = datetime(2024, 1, 2, 3, 4, 5)
    def user(uid):
        return dict(id=uid, email=f'migration-{uid}@example.test', full_name='Migration fixture',
                    hashed_password='not-a-login', role='consumer', preferred_language='en',
                    is_active=uid != 2, is_verified=True, mfa_enabled=False,
                    created_at=created, updated_at=created)
    def brand(bid, uid):
        return dict(id=bid, user_id=uid, brand_name=f'Migration fixture {bid}', slug=f'migration-{bid}',
                    commission_rate=15, return_rate_benchmark=0, current_return_rate=0,
                    is_verified=True, created_at=created)
    with engine.begin() as conn:
        conn.execute(users.insert(), [user(1), user(2), user(3)])
        conn.execute(brands.insert(), [brand(10, 1), brand(20, 2)])
    _alembic(url, 'up', 'head')
    members = Table('brand_memberships', MetaData(), autoload_with=engine)
    with engine.begin() as conn:
        rows = conn.execute(select(members).order_by(members.c.brand_id)).mappings().all()
        assert [(r['brand_id'], r['user_id'], r['role']) for r in rows] == [(10, 1, 'owner'), (20, 2, 'owner')]
        assert all(r['created_at'].replace(tzinfo=None) == created for r in rows)
        assert conn.execute(select(brands.c.id, brands.c.user_id).order_by(brands.c.id)).all() == [(10, 1), (20, 2)]
        assert set(conn.execute(select(users.c.role)).scalars()) == {'consumer'}
        if engine.dialect.name == 'postgresql':
            # A previous application version writes only the legacy owner
            # pointer. The migration trigger creates its membership atomically.
            conn.execute(brands.insert(), brand(30, 3))
            assert conn.execute(select(members.c.role).where(members.c.user_id == 3)).scalar_one() == 'owner'
