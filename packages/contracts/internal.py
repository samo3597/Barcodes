"""Versioned internal publication contracts between Server 1 and Server 2."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from packages.contracts.common import StrictContract
from packages.contracts.product import PublicProduct


class ProductUpsertedEvent(StrictContract):
    """Idempotent product snapshot emitted from the Server 1 outbox."""

    event_id: UUID
    event_type: Literal["product.upserted", "product.disabled"] = "product.upserted"
    aggregate_id: str = Field(min_length=8, max_length=14)
    aggregate_version: int = Field(ge=1)
    occurred_at: datetime
    payload: PublicProduct


class PublicationApplyResponse(StrictContract):
    """Stable acknowledgement persisted for event-id replays."""

    event_id: UUID
    barcode: str
    version: int = Field(ge=1)
    status: Literal["applied", "ignored_stale"]
    version_gap: bool = False
