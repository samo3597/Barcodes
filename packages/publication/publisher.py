"""HMAC-authenticated at-least-once delivery from the transactional outbox."""

import hashlib
import hmac
import json
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.contracts import ProductUpsertedEvent
from packages.persistence.server1.canonical_repositories import claim_outbox_event
from packages.persistence.server1.models import OutboxEvent


class PublisherError(RuntimeError):
    """A transient internal publication failure."""


class HttpEventPublisher:
    """Send one signed event to Server 2's idempotent receiver."""

    def __init__(self, base_url: str, secret: str, timeout_seconds: float = 10.0) -> None:
        if not secret:
            raise ValueError("internal sync secret is required")
        self.base_url = base_url.rstrip("/")
        self.secret = secret.encode()
        self.timeout = timeout_seconds

    async def publish(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        timestamp = str(int(datetime.now(UTC).timestamp()))
        event_id = str(payload["event_id"])
        signed = b".".join([timestamp.encode(), event_id.encode(), body])
        signature = hmac.new(self.secret, signed, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": event_id,
            "X-Event-Id": event_id,
            "X-Signature-Timestamp": timestamp,
            "X-Signature-SHA256": signature,
        }
        barcode = str(payload["aggregate_id"])
        url = f"{self.base_url}/internal/v1/products/{barcode}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(url, content=body, headers=headers)
        if response.status_code not in {200, 201, 202, 204}:
            raise PublisherError(f"Server 2 returned HTTP {response.status_code}")


async def publish_next_event(
    session_factory: async_sessionmaker[AsyncSession],
    send: Callable[[dict[str, Any]], Awaitable[None]],
) -> tuple[str, int | None]:
    """Claim, send, and finalize one event; return state and optional retry delay."""

    async with session_factory() as session:
        event = await claim_outbox_event(session)
        if event is None:
            return "empty", None
        event_id = event.id
        payload = ProductUpsertedEvent.model_validate(event.payload).model_dump(mode="json")
        attempts = event.attempts
        max_attempts = event.max_attempts
    try:
        await send(payload)
    except (httpx.HTTPError, PublisherError, TimeoutError) as error:
        delay = min(900, 2 ** min(attempts, 9) + random.SystemRandom().randint(0, 10))
        async with session_factory() as session:
            event = await session.get(OutboxEvent, event_id)
            if event is None:
                raise RuntimeError("claimed outbox event disappeared") from error
            event.last_error = str(error)[:2_000]
            if attempts >= max_attempts:
                event.status = "dead_letter"
                event.next_attempt_at = None
                state = "dead_letter"
                retry_delay = None
            else:
                event.status = "retry_scheduled"
                event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
                state = "retry_scheduled"
                retry_delay = delay
            await session.commit()
        return state, retry_delay
    async with session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        if event is None:
            raise RuntimeError("claimed outbox event disappeared")
        event.status = "delivered"
        event.delivered_at = datetime.now(UTC)
        event.last_error = None
        await session.commit()
    return "delivered", None
