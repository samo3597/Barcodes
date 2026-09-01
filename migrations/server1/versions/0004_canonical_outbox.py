"""Create canonical versions, image lifecycle, and transactional outbox.

Revision ID: server1_0004
Revises: server1_0003
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "server1_0004"
down_revision: str | None = "server1_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("public_url", sa.String(length=2000), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_assets"),
        sa.UniqueConstraint("content_hash", name="uq_image_assets_content_hash"),
        sa.UniqueConstraint("storage_key", name="uq_image_assets_storage_key"),
    )
    op.create_table(
        "canonical_products",
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("barcode", name="pk_canonical_products"),
    )
    op.create_table(
        "image_fetches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("image_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_image_fetches_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["ai_result_id"],
            ["ai_results.id"],
            name="fk_image_fetches_ai_result_id_ai_results",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["image_asset_id"],
            ["image_assets.id"],
            name="fk_image_fetches_image_asset_id_image_assets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_fetches"),
        sa.UniqueConstraint("ai_result_id", name="uq_image_fetches_ai_result_id"),
    )
    op.create_index("ix_image_fetches_status", "image_fetches", ["status"])
    op.create_index("ix_image_fetches_image_asset_id", "image_fetches", ["image_asset_id"])
    op.create_table(
        "product_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("origin", sa.String(length=30), nullable=False),
        sa.Column("origin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("image_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "origin IN ('source_merge', 'ai_run', 'manual_decision')",
            name="ck_product_versions_origin_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["barcode"],
            ["canonical_products.barcode"],
            name="fk_product_versions_barcode_canonical_products",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["image_asset_id"],
            ["image_assets.id"],
            name="fk_product_versions_image_asset_id_image_assets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_versions"),
        sa.UniqueConstraint("barcode", "version", name="uq_product_versions_barcode_version"),
    )
    op.create_index("ix_product_versions_image_asset_id", "product_versions", ["image_asset_id"])
    op.create_index(
        "ix_product_versions_barcode_created",
        "product_versions",
        ["barcode", "created_at"],
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=14), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="8", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'retry_scheduled', 'delivered', 'dead_letter')",
            name="ck_outbox_events_status_allowed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
        sa.UniqueConstraint(
            "event_type",
            "aggregate_id",
            "aggregate_version",
            name="uq_outbox_events_aggregate_version",
        ),
    )
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_index("ix_outbox_events_next_attempt_at", "outbox_events", ["next_attempt_at"])
    op.create_index(
        "ix_outbox_events_ready",
        "outbox_events",
        ["status", "next_attempt_at", "created_at"],
    )
    # Alembic applies the metadata naming convention to explicitly named checks.
    # Normalize the resulting doubled names to the model-visible stable names.
    op.execute(
        "ALTER TABLE image_fetches RENAME CONSTRAINT "
        "ck_image_fetches_ck_image_fetches_status_allowed TO ck_image_fetches_status_allowed"
    )
    op.execute(
        "ALTER TABLE product_versions RENAME CONSTRAINT "
        "ck_product_versions_ck_product_versions_origin_allowed "
        "TO ck_product_versions_origin_allowed"
    )
    op.execute(
        "ALTER TABLE outbox_events RENAME CONSTRAINT "
        "ck_outbox_events_ck_outbox_events_status_allowed TO ck_outbox_events_status_allowed"
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_ready", table_name="outbox_events")
    op.drop_index("ix_outbox_events_next_attempt_at", table_name="outbox_events")
    op.drop_index("ix_outbox_events_status", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_product_versions_barcode_created", table_name="product_versions")
    op.drop_index("ix_product_versions_image_asset_id", table_name="product_versions")
    op.drop_table("product_versions")
    op.drop_index("ix_image_fetches_image_asset_id", table_name="image_fetches")
    op.drop_index("ix_image_fetches_status", table_name="image_fetches")
    op.drop_table("image_fetches")
    op.drop_table("canonical_products")
    op.drop_table("image_assets")
