"""SQLAlchemy models owned exclusively by Server 1."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
from packages.persistence.base import Server1Base


class TimestampMixin:
    """Database-generated creation and update timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Source(TimestampMixin, Server1Base):
    """An external system allowed to push product data."""

    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="status_allowed"),)

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    field_priorities: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    api_keys: Mapped[list["SourceApiKey"]] = relationship(back_populates="source")
    batches: Mapped[list["ImportBatch"]] = relationship(back_populates="source")
    revisions: Mapped[list["SourceProductRevision"]] = relationship(back_populates="source")


class SourceApiKey(TimestampMixin, Server1Base):
    """Hashed bearer credential scoped to exactly one source."""

    __tablename__ = "source_api_keys"
    __table_args__ = (CheckConstraint("status IN ('active', 'revoked')", name="status_allowed"),)

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_prefix: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source] = relationship(back_populates="api_keys")


class ImportBatch(TimestampMixin, Server1Base):
    """Idempotent acceptance record for one source request."""

    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("source_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('accepted', 'processing', 'completed', 'failed')",
            name="status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    external_batch_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="accepted", nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    source: Mapped[Source] = relationship(back_populates="batches")
    revisions: Mapped[list["SourceProductRevision"]] = relationship(back_populates="batch")
    items: Mapped[list["ImportBatchItem"]] = relationship(back_populates="batch")


class SourceProductRevision(Server1Base):
    """Immutable source item payload retained for audit and reprocessing."""

    __tablename__ = "source_product_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id", "payload_hash"),
        Index("ix_source_product_revisions_barcode_created", "barcode", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    barcode: Mapped[str] = mapped_column(String(14), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    source: Mapped[Source] = relationship(back_populates="revisions")
    batch: Mapped[ImportBatch] = relationship(back_populates="revisions")
    batch_items: Mapped[list["ImportBatchItem"]] = relationship(back_populates="revision")


class ImportBatchItem(Server1Base):
    """Association from every accepted batch item to its deduplicated revision."""

    __tablename__ = "import_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "position", name="uq_import_batch_items_position"),
        UniqueConstraint(
            "batch_id",
            "source_record_id",
            name="uq_import_batch_items_source_record",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_product_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    barcode: Mapped[str] = mapped_column(String(14), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    batch: Mapped[ImportBatch] = relationship(back_populates="items")
    revision: Mapped[SourceProductRevision] = relationship(back_populates="batch_items")


class ProductCandidate(Server1Base):
    """Immutable normalized snapshot used as the exact input to an AI run."""

    __tablename__ = "product_candidates"
    __table_args__ = (
        UniqueConstraint(
            "barcode",
            "input_hash",
            "schema_version",
            name="uq_product_candidates_input",
        ),
        Index("ix_product_candidates_barcode_created", "barcode", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    barcode: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_revision_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PostgreSQLUUID(as_uuid=True)),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AIJob(TimestampMixin, Server1Base):
    """Durable provider batch state safe under at-least-once task delivery."""

    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "model",
            "prompt_version",
            "request_hash",
            name="uq_ai_jobs_request",
        ),
        UniqueConstraint(
            "provider",
            "provider_batch_id",
            name="uq_ai_jobs_provider_batch",
        ),
        CheckConstraint(
            "status IN ('pending', 'submitted', 'processing', 'completed', 'retry_scheduled', "
            "'failed', 'cancelled')",
            name="status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PostgreSQLUUID(as_uuid=True)),
        nullable=False,
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provider_batch_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIResult(Server1Base):
    """Immutable raw and parsed result for one candidate/model/prompt combination."""

    __tablename__ = "ai_results"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "provider",
            "model",
            "prompt_version",
            name="uq_ai_results_candidate_model_prompt",
        ),
        UniqueConstraint("job_id", "candidate_id", name="uq_ai_results_job_candidate"),
        CheckConstraint("status IN ('valid', 'schema_failed')", name="status_allowed"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("product_candidates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    parsed_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    warnings: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
