"""HMAC verification for Server 1 publication requests."""

import hashlib
import hmac
import time
from uuid import UUID

from fastapi import HTTPException, status


def verify_internal_signature(
    *,
    body: bytes,
    event_id: UUID,
    timestamp: str,
    signature: str,
    secret: str | None,
    replay_window_seconds: int,
    now: int | None = None,
) -> None:
    """Reject missing config, stale timestamps, and non-canonical signatures."""

    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "internal_sync_not_configured",
                "message": "Internal publication is not configured",
                "retryable": True,
            },
        )
    try:
        supplied_time = int(timestamp)
    except ValueError as error:
        raise _invalid_signature() from error
    current_time = int(time.time()) if now is None else now
    if abs(current_time - supplied_time) > replay_window_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "signature_expired",
                "message": "Internal signature timestamp is outside the replay window",
                "retryable": False,
            },
        )
    signed = b".".join([timestamp.encode(), str(event_id).encode(), body])
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise _invalid_signature()


def _invalid_signature() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_internal_signature",
            "message": "Internal request signature is invalid",
            "retryable": False,
        },
    )
