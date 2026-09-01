"""Create Server 2 quota and usage accounting tables.

Revision ID: server2_0003
Revises: server2_0002
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "server2_0003"
down_revision: str | None = "server2_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monthly_product_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("billing_month", sa.Date(), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("first_api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "first_requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["first_api_key_id"],
            ["tenant_api_keys.id"],
            name="fk_monthly_product_usage_first_api_key_id_tenant_api_keys",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_monthly_product_usage_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_monthly_product_usage"),
        sa.UniqueConstraint(
            "tenant_id",
            "billing_month",
            "barcode",
            name="uq_monthly_product_usage_tenant_month_barcode",
        ),
    )
    op.create_index(
        "ix_monthly_product_usage_tenant_month",
        "monthly_product_usage",
        ["tenant_id", "billing_month"],
    )
    op.create_table(
        "daily_usage_rollups",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("rate_limited_count", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("request_count >= 0", name="request_count_nonnegative"),
        sa.CheckConstraint("rate_limited_count >= 0", name="rate_limited_count_nonnegative"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_daily_usage_rollups_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "usage_date", name="pk_daily_usage_rollups"),
    )


def downgrade() -> None:
    op.drop_table("daily_usage_rollups")
    op.drop_index("ix_monthly_product_usage_tenant_month", table_name="monthly_product_usage")
    op.drop_table("monthly_product_usage")
