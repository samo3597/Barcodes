"""SQLAlchemy models owned exclusively by Server 2."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.domain.identifiers import new_uuid7
from packages.persistence.base import Server2Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Tenant(TimestampMixin, Server2Base):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="status_allowed"),)

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=new_uuid7
    )
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True, nullable=False)
    plan_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    api_keys: Mapped[list["TenantApiKey"]] = relationship(back_populates="tenant")


class TenantApiKey(TimestampMixin, Server2Base):
    __tablename__ = "tenant_api_keys"
    __table_args__ = (CheckConstraint("status IN ('active', 'revoked')", name="status_allowed"),)

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=new_uuid7
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    key_prefix: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant] = relationship(back_populates="api_keys")


class Category(TimestampMixin, Server2Base):
    __tablename__ = "categories"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="status_allowed"),)

    category_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.category_id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", index=True, nullable=False)


class PublishedProduct(Server2Base):
    """Current typed snapshot used by latency-sensitive public reads."""

    __tablename__ = "published_products"
    __table_args__ = (
        CheckConstraint(
            "quality_status IN ('ai_processed', 'source_complete', 'processing_failed', "
            "'disabled')",
            name="quality_status_allowed",
        ),
        Index("ix_published_products_updated_at", "updated_at"),
    )

    barcode: Mapped[str] = mapped_column(String(14), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2_000))
    atg_code: Mapped[str] = mapped_column(String(4), nullable=False)
    vat: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_weighted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.category_id", ondelete="RESTRICT"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(30), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppliedEvent(Server2Base):
    """Durable idempotency result for an internal publication event."""

    __tablename__ = "applied_events"

    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(14), index=True, nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChangeEvent(Server2Base):
    """Immutable cursor source; the public changes endpoint arrives in W7."""

    __tablename__ = "change_events"
    __table_args__ = (
        UniqueConstraint("barcode", "version", name="uq_change_events_barcode_version"),
        CheckConstraint("change_type IN ('upsert', 'disabled')", name="type_allowed"),
    )

    change_id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("applied_events.event_id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    barcode: Mapped[str] = mapped_column(String(14), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeedbackEvent(Server2Base):
    """Append-only operator feedback, isolated from the published read model."""

    __tablename__ = "feedback_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_feedback_tenant_idempotency"),
        CheckConstraint("action IN ('accepted', 'corrected', 'rejected')", name="action_allowed"),
        Index("ix_feedback_events_received_at", "received_at"),
    )

    sequence_id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), default=new_uuid7, unique=True, nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    api_key_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant_api_keys.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    barcode: Mapped[str] = mapped_column(String(14), index=True, nullable=False)
    product_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    operator_ref: Mapped[str | None] = mapped_column(String(255))
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    client_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MonthlyProductUsage(Server2Base):
    """Authoritative fact that a tenant received a barcode in a billing month."""

    __tablename__ = "monthly_product_usage"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "billing_month",
            "barcode",
            name="uq_monthly_product_usage_tenant_month_barcode",
        ),
        Index("ix_monthly_product_usage_tenant_month", "tenant_id", "billing_month"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=new_uuid7
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    billing_month: Mapped[date] = mapped_column(Date, nullable=False)
    barcode: Mapped[str] = mapped_column(String(14), nullable=False)
    first_api_key_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant_api_keys.id", ondelete="SET NULL")
    )
    first_requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyUsageRollup(Server2Base):
    """Persistent daily request report; Redis remains the real-time limiter."""

    __tablename__ = "daily_usage_rollups"
    __table_args__ = (
        CheckConstraint("request_count >= 0", name="request_count_nonnegative"),
        CheckConstraint("rate_limited_count >= 0", name="rate_limited_count_nonnegative"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limited_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
