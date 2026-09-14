"""Add durable retention floor and hot-path indexes.

Revision ID: server2_0005
Revises: server2_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "server2_0005"
down_revision: str | None = "server2_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("feedback_events", "request_id", type_=sa.String(128), existing_nullable=False)
    op.create_index("ix_change_events_changed_at", "change_events", ["changed_at"])
    op.create_index(
        "ix_monthly_product_usage_tenant_barcode", "monthly_product_usage", ["tenant_id", "barcode"]
    )
    op.create_table(
        "change_retention_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expired_through", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name="singleton"),
        sa.CheckConstraint("expired_through >= 0", name="floor_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_change_retention_state"),
    )


def downgrade() -> None:
    op.drop_table("change_retention_state")
    op.drop_index("ix_monthly_product_usage_tenant_barcode", table_name="monthly_product_usage")
    op.drop_index("ix_change_events_changed_at", table_name="change_events")
    # Keep the expanded request-ID column: narrowing may destroy valid correlation IDs.
