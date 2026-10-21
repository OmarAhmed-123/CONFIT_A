"""0043 · catalog_import_jobs — carry the file, the run's state, and its lease.

WHY: the import endpoint answered `202 Accepted` and then performed the whole
import inside the request. `catalog_ingest` was routed in ``celery_app`` but the
task it named did not exist, and the job table could not have supported an
asynchronous run anyway:

* it had nowhere to put the CSV, so a worker had nothing to process after the
  request ended;
* it had no attempt counter, so a retry was indistinguishable from a first run;
* it had no heartbeat or lease, so a job left in ``processing`` by a killed
  worker could never be told apart from one that was genuinely running;
* it had no per-run configuration (target branch, notification opt-in, actor),
  so a worker could not reproduce what the request had asked for;
* it had no progress column, so "queued" and "row 900 of 1000" looked identical.

This migration adds exactly those, all nullable or defaulted so existing rows and
older deployments stay readable:

    payload_text        the CSV as received (UTF-8) — the durable work item
    payload_sha256      digest, to correlate a retry with the same bytes
    target_store_id     branch the import was aimed at
    send_notifications  the request's explicit opt-in
    actor_id            who confirmed it (audit, notifications)
    attempts            how many times a worker has claimed this job
    processed_rows      real progress, updated as rows are handled
    heartbeat_at        lease: a stale value means the worker died
    last_error          one-line reason for the most recent failure
    celery_task_id      the dispatched task id, for operator correlation

`payload_text` is cleared when a job reaches a terminal state, so the table does
not accumulate catalogues; it is kept after a failure precisely so a retry can
re-run the same bytes.

Single-head chain: 0042_photo_unique_with_index -> 0043_import_job_payload.
(0041_photo_index added `photo_index`; 0042 fixed the uniqueness rule to include
it — the gallery needed both before an import could register a second photograph.)
Additive only (new nullable/defaulted columns, one index). SQLite-safe: no table
rebuild. PostgreSQL-safe: constant defaults, no rewrite.

Revision ID: 0043_import_job_payload
Revises: 0042_photo_unique_with_index
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0043_import_job_payload"
down_revision = "0042_photo_unique_with_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_import_jobs", sa.Column("payload_text", sa.Text(), nullable=True))
    op.add_column("catalog_import_jobs", sa.Column("payload_sha256", sa.String(length=64), nullable=True))
    op.add_column("catalog_import_jobs", sa.Column("target_store_id", sa.Integer(), nullable=True))
    op.add_column(
        "catalog_import_jobs",
        sa.Column("send_notifications", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("catalog_import_jobs", sa.Column("actor_id", sa.Integer(), nullable=True))
    op.add_column(
        "catalog_import_jobs",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "catalog_import_jobs",
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("catalog_import_jobs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    op.add_column("catalog_import_jobs", sa.Column("last_error", sa.String(length=500), nullable=True))
    op.add_column("catalog_import_jobs", sa.Column("celery_task_id", sa.String(length=100), nullable=True))
    # The recovery sweep looks for work that is still open, so index exactly that.
    op.create_index(
        "ix_catalog_import_open_jobs",
        "catalog_import_jobs",
        ["status", "heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_import_open_jobs", table_name="catalog_import_jobs")
    for column in (
        "celery_task_id",
        "last_error",
        "heartbeat_at",
        "processed_rows",
        "attempts",
        "actor_id",
        "send_notifications",
        "target_store_id",
        "payload_sha256",
        "payload_text",
    ):
        op.drop_column("catalog_import_jobs", column)
