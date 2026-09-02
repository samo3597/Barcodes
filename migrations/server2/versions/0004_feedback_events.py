"""Create append-only tenant feedback storage.

Revision ID: server2_0004
Revises: server2_0003
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "server2_0004"
down_revision: str | None = "server2_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback_events",
        sa.Column(
            "sequence_id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("product_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("operator_ref", sa.String(length=255), nullable=True),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("client_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('accepted', 'corrected', 'rejected')", name="action_allowed"
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["tenant_api_keys.id"],
            name="fk_feedback_events_api_key_id_tenant_api_keys",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_feedback_events_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sequence_id", name="pk_feedback_events"),
        sa.UniqueConstraint("event_id", name="uq_feedback_events_event_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_feedback_tenant_idempotency"),
    )
    op.create_index("ix_feedback_events_barcode", "feedback_events", ["barcode"])
    op.create_index("ix_feedback_events_received_at", "feedback_events", ["received_at"])
    op.create_index("ix_feedback_events_tenant_id", "feedback_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_events_tenant_id", table_name="feedback_events")
    op.drop_index("ix_feedback_events_received_at", table_name="feedback_events")
    op.drop_index("ix_feedback_events_barcode", table_name="feedback_events")
    op.drop_table("feedback_events")
