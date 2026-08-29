"""Create normalized candidates and immutable AI processing history.

Revision ID: server1_0003
Revises: server1_0002
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "server1_0003"
down_revision: str | None = "server1_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sources RENAME CONSTRAINT "
        "ck_sources_ck_sources_status_allowed TO ck_sources_status_allowed"
    )
    op.execute(
        "ALTER TABLE source_api_keys RENAME CONSTRAINT "
        "ck_source_api_keys_ck_source_api_keys_status_allowed "
        "TO ck_source_api_keys_status_allowed"
    )
    op.execute(
        "ALTER TABLE import_batches RENAME CONSTRAINT "
        "ck_import_batches_ck_import_batches_status_allowed "
        "TO ck_import_batches_status_allowed"
    )

    op.create_table(
        "import_batch_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name="fk_import_batch_items_batch_id_import_batches",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["source_product_revisions.id"],
            name="fk_import_batch_items_revision_id_source_product_revisions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_batch_items"),
        sa.UniqueConstraint("batch_id", "position", name="uq_import_batch_items_position"),
        sa.UniqueConstraint(
            "batch_id",
            "source_record_id",
            name="uq_import_batch_items_source_record",
        ),
    )
    op.create_index("ix_import_batch_items_batch_id", "import_batch_items", ["batch_id"])
    op.create_index("ix_import_batch_items_revision_id", "import_batch_items", ["revision_id"])
    op.execute(
        """
        INSERT INTO import_batch_items
            (id, batch_id, revision_id, source_record_id, barcode, position, created_at)
        SELECT
            id,
            batch_id,
            id,
            source_record_id,
            barcode,
            ROW_NUMBER() OVER (PARTITION BY batch_id ORDER BY created_at, id) - 1,
            created_at
        FROM source_product_revisions
        """
    )

    op.create_table(
        "product_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source_revision_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_candidates"),
        sa.UniqueConstraint(
            "barcode",
            "input_hash",
            "schema_version",
            name="uq_product_candidates_input",
        ),
    )
    op.create_index("ix_product_candidates_barcode", "product_candidates", ["barcode"])
    op.create_index(
        "ix_product_candidates_barcode_created",
        "product_candidates",
        ["barcode", "created_at"],
    )

    op.create_table(
        "ai_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "candidate_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_batch_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="4", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'submitted', 'processing', 'completed', 'retry_scheduled', "
            "'failed', 'cancelled')",
            name="status_allowed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_jobs"),
        sa.UniqueConstraint(
            "provider",
            "model",
            "prompt_version",
            "request_hash",
            name="uq_ai_jobs_request",
        ),
        sa.UniqueConstraint(
            "provider",
            "provider_batch_id",
            name="uq_ai_jobs_provider_batch",
        ),
    )
    op.create_index("ix_ai_jobs_status", "ai_jobs", ["status"])
    op.create_index("ix_ai_jobs_next_attempt_at", "ai_jobs", ["next_attempt_at"])

    op.create_table(
        "ai_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("parsed_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "warnings",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("ARRAY[]::text[]"),
            nullable=False,
        ),
        sa.Column(
            "usage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["product_candidates.id"],
            name="fk_ai_results_candidate_id_product_candidates",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ai_jobs.id"],
            name="fk_ai_results_job_id_ai_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_results"),
        sa.CheckConstraint(
            "status IN ('valid', 'schema_failed')",
            name="status_allowed",
        ),
        sa.UniqueConstraint(
            "candidate_id",
            "provider",
            "model",
            "prompt_version",
            name="uq_ai_results_candidate_model_prompt",
        ),
        sa.UniqueConstraint("job_id", "candidate_id", name="uq_ai_results_job_candidate"),
    )
    op.create_index("ix_ai_results_job_id", "ai_results", ["job_id"])
    op.create_index("ix_ai_results_candidate_id", "ai_results", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_results_candidate_id", table_name="ai_results")
    op.drop_index("ix_ai_results_job_id", table_name="ai_results")
    op.drop_table("ai_results")
    op.drop_index("ix_ai_jobs_next_attempt_at", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_status", table_name="ai_jobs")
    op.drop_table("ai_jobs")
    op.drop_index("ix_product_candidates_barcode_created", table_name="product_candidates")
    op.drop_index("ix_product_candidates_barcode", table_name="product_candidates")
    op.drop_table("product_candidates")
    op.drop_index("ix_import_batch_items_revision_id", table_name="import_batch_items")
    op.drop_index("ix_import_batch_items_batch_id", table_name="import_batch_items")
    op.drop_table("import_batch_items")
    op.execute(
        "ALTER TABLE import_batches RENAME CONSTRAINT "
        "ck_import_batches_status_allowed TO ck_import_batches_ck_import_batches_status_allowed"
    )
    op.execute(
        "ALTER TABLE source_api_keys RENAME CONSTRAINT "
        "ck_source_api_keys_status_allowed "
        "TO ck_source_api_keys_ck_source_api_keys_status_allowed"
    )
    op.execute(
        "ALTER TABLE sources RENAME CONSTRAINT "
        "ck_sources_status_allowed TO ck_sources_ck_sources_status_allowed"
    )
