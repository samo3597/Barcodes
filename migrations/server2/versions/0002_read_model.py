"""Create Server 2 tenants, product read model, and event history.

Revision ID: server2_0002
Revises: server2_0001
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "server2_0002"
down_revision: str | None = "server2_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "plan_config",
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
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="status_allowed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.UniqueConstraint("code", name="uq_tenants_code"),
    )
    op.create_index("ix_tenants_status", "tenants", ["status"])
    op.create_table(
        "tenant_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_prefix", sa.String(length=12), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(length=50)), nullable=False),
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
            name="status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_api_keys_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_api_keys"),
        sa.UniqueConstraint("key_prefix", name="uq_tenant_api_keys_key_prefix"),
    )
    op.create_index("ix_tenant_api_keys_tenant_id", "tenant_api_keys", ["tenant_id"])
    op.create_table(
        "categories",
        sa.Column("category_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.category_id"],
            name="fk_categories_parent_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("category_id", name="pk_categories"),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_index("ix_categories_status", "categories", ["status"])
    op.create_table(
        "published_products",
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("image_url", sa.String(length=2000), nullable=True),
        sa.Column("atg_code", sa.String(length=4), nullable=False),
        sa.Column("vat", sa.Boolean(), nullable=False),
        sa.Column("is_weighted", sa.Boolean(), nullable=False),
        sa.Column("category_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=30), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "quality_status IN ('ai_processed', 'source_complete', 'processing_failed', "
            "'disabled')",
            name="quality_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.category_id"],
            name="fk_published_products_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("barcode", name="pk_published_products"),
    )
    op.create_index("ix_published_products_category_id", "published_products", ["category_id"])
    op.create_index("ix_published_products_updated_at", "published_products", ["updated_at"])
    op.create_table(
        "applied_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=14), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_applied_events"),
    )
    op.create_index("ix_applied_events_aggregate_id", "applied_events", ["aggregate_id"])
    op.create_table(
        "change_events",
        sa.Column("change_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("change_type", sa.String(length=20), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "change_type IN ('upsert', 'disabled')",
            name="type_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["applied_events.event_id"],
            name="fk_change_events_event_id_applied_events",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("change_id", name="pk_change_events"),
        sa.UniqueConstraint("event_id", name="uq_change_events_event_id"),
        sa.UniqueConstraint("barcode", "version", name="uq_change_events_barcode_version"),
    )
    op.create_index("ix_change_events_barcode", "change_events", ["barcode"])


def downgrade() -> None:
    op.drop_index("ix_change_events_barcode", table_name="change_events")
    op.drop_table("change_events")
    op.drop_index("ix_applied_events_aggregate_id", table_name="applied_events")
    op.drop_table("applied_events")
    op.drop_index("ix_published_products_updated_at", table_name="published_products")
    op.drop_index("ix_published_products_category_id", table_name="published_products")
    op.drop_table("published_products")
    op.drop_index("ix_categories_status", table_name="categories")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ix_tenant_api_keys_tenant_id", table_name="tenant_api_keys")
    op.drop_table("tenant_api_keys")
    op.drop_index("ix_tenants_status", table_name="tenants")
    op.drop_table("tenants")
