"""Internal HMAC authentication and replay-window rules."""

import hashlib
import hmac
from uuid import uuid4

import pytest
from fastapi import HTTPException

from apps.public_api.internal_auth import verify_internal_signature


def signature(secret: str, timestamp: str, event_id: object, body: bytes) -> str:
    signed = b".".join([timestamp.encode(), str(event_id).encode(), body])
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def test_valid_signature_is_accepted() -> None:
    event_id = uuid4()
    body = b'{"event":"body"}'
    timestamp = "1000"

    verify_internal_signature(
        body=body,
        event_id=event_id,
        timestamp=timestamp,
        signature=signature("secret", timestamp, event_id, body),
        secret="secret",
        replay_window_seconds=300,
        now=1100,
    )


def test_changed_body_and_expired_timestamp_are_rejected() -> None:
    event_id = uuid4()
    valid = signature("secret", "1000", event_id, b"original")
    with pytest.raises(HTTPException) as changed:
        verify_internal_signature(
            body=b"changed",
            event_id=event_id,
            timestamp="1000",
            signature=valid,
            secret="secret",
            replay_window_seconds=300,
            now=1100,
        )
    assert changed.value.status_code == 401

    with pytest.raises(HTTPException) as expired:
        verify_internal_signature(
            body=b"original",
            event_id=event_id,
            timestamp="1000",
            signature=valid,
            secret="secret",
            replay_window_seconds=300,
            now=1400,
        )
    assert expired.value.detail["code"] == "signature_expired"
