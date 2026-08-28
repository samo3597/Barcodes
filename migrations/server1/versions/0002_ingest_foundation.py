"""Create source credentials, batches, and immutable revisions.

Revision ID: server1_0002
Revises: server1_0001
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "server1_0002"
down_revision: str | None = "server1_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "field_priorities",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_sources_status_allowed"),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("name", name="uq_sources_name"),
    )
    op.create_index("ix_sources_status", "sources", ["status"])

    op.create_table(
        "source_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_prefix", sa.String(length=12), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(length=50)),
            server_default=sa.text("ARRAY[]::varchar[]"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_source_api_keys_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_api_keys_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_api_keys"),
        sa.UniqueConstraint("key_prefix", name="uq_source_api_keys_key_prefix"),
    )
    op.create_index("ix_source_api_keys_source_id", "source_api_keys", ["source_id"])

    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("external_batch_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("received", sa.Integer(), nullable=False),
        sa.Column("validated", sa.Integer(), nullable=False),
        sa.Column("rejected", sa.Integer(), nullable=False),
        sa.Column("ai_pending", sa.Integer(), nullable=False),
        sa.Column("published", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('accepted', 'processing', 'completed', 'failed')",
            name="ck_import_batches_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_import_batches_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_batches"),
        sa.UniqueConstraint(
            "source_id",
            "idempotency_key",
            name="uq_import_batches_source_id",
        ),
    )
    op.create_index("ix_import_batches_source_id", "import_batches", ["source_id"])
    op.create_index("ix_import_batches_status", "import_batches", ["status"])

    op.create_table(
        "source_product_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["import_batches.id"],
            name="fk_source_product_revisions_batch_id_import_batches",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_product_revisions_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_product_revisions"),
        sa.UniqueConstraint(
            "source_id",
            "source_record_id",
            "payload_hash",
            name="uq_source_product_revisions_source_id",
        ),
    )
    op.create_index(
        "ix_source_product_revisions_barcode_created",
        "source_product_revisions",
        ["barcode", "created_at"],
    )
    op.create_index(
        "ix_source_product_revisions_batch_id",
        "source_product_revisions",
        ["batch_id"],
    )
    op.create_index(
        "ix_source_product_revisions_source_id",
        "source_product_revisions",
        ["source_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_source_product_revisions_source_id", table_name="source_product_revisions")
    op.drop_index("ix_source_product_revisions_batch_id", table_name="source_product_revisions")
    op.drop_index(
        "ix_source_product_revisions_barcode_created",
        table_name="source_product_revisions",
    )
    op.drop_table("source_product_revisions")
    op.drop_index("ix_import_batches_status", table_name="import_batches")
    op.drop_index("ix_import_batches_source_id", table_name="import_batches")
    op.drop_table("import_batches")
    op.drop_index("ix_source_api_keys_source_id", table_name="source_api_keys")
    op.drop_table("source_api_keys")
    op.drop_index("ix_sources_status", table_name="sources")
    op.drop_table("sources")
