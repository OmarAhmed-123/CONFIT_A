"""tryon_jobs retention lifecycle (expires_at, consent_retained).

Revision ID: 0020_vton_job_retention
Revises: 0019_product_sleeve_length
Create Date: 2026-09-19

Root cause (2026-09-19 complete gap audit, privacy lifecycle):
``tryon_jobs.input_person_image_url`` stores the user-uploaded person
photo (data URL), but the job row had NO retention columns — only
``tryon_sessions`` carried ``expires_at``/``consent_retained`` — so the
GDPR Article 17 24-hour purge (``purge_expired_sessions_task``) could
never reach the person photos persisted on job rows. They would be
retained indefinitely.

This migration adds the two retention columns to ``tryon_jobs`` so the
purge daemon (and the opportunistic read-time purge) can enforce the
same 24h/consent lifecycle on job rows as on session rows. Existing
rows are back-filled with ``created_at + 24h`` (unconsented default) so
pre-existing jobs become purge-eligible immediately rather than
immortal. The back-fill is executed in Python so it is portable across
SQLite (dev) and Postgres (production).

Idempotent inspector-guarded delta, same style as 0016-0018.
"""
from typing import Sequence, Union
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "0020_vton_job_retention"
down_revision: Union[str, None] = "0019_product_sleeve_length"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind, table: str) -> set:
    insp = inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "tryon_jobs" not in inspect(bind).get_table_names():
        return
    cols = _columns(bind, "tryon_jobs")
    if "expires_at" not in cols:
        op.add_column("tryon_jobs", sa.Column("expires_at", sa.DateTime(), nullable=True))
    if "consent_retained" not in cols:
        op.add_column(
            "tryon_jobs", sa.Column("consent_retained", sa.Boolean(), nullable=True)
        )
    # Back-fill (portable Python, no dialect-specific interval syntax):
    # jobs created before this migration had no retention; treat them as
    # unconsented with created_at + 24h so the purge daemon reaches them
    # (BRD: 24h default retention, never infinite).
    rows = bind.execute(
        text(
            "SELECT id, created_at FROM tryon_jobs "
            "WHERE (expires_at IS NULL OR consent_retained IS NULL) AND created_at IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        created = row[1]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        bind.execute(
            text("UPDATE tryon_jobs SET expires_at = :exp, consent_retained = :consent WHERE id = :id"),
            {
                "exp": (created + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"),
                "consent": False,
                "id": row[0],
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "tryon_jobs" not in inspect(bind).get_table_names():
        return
    cols = _columns(bind, "tryon_jobs")
    if "consent_retained" in cols:
        op.drop_column("tryon_jobs", "consent_retained")
    if "expires_at" in cols:
        op.drop_column("tryon_jobs", "expires_at")
