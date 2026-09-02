"""Opaque, tenant-bound HMAC cursors for the public changes feed."""

import base64
import hashlib
import hmac
import json
from typing import cast
from uuid import UUID


class InvalidCursorError(ValueError):
    """The cursor is malformed, tampered with, or belongs to another tenant."""


def encode_change_cursor(change_id: int, tenant_id: UUID, secret: str) -> str:
    payload = json.dumps(
        {"v": 1, "tenant_id": str(tenant_id), "change_id": change_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return f"{_encode(payload)}.{_encode(signature)}"


def decode_change_cursor(cursor: str, tenant_id: UUID, secret: str) -> int:
    try:
        encoded_payload, encoded_signature = cursor.split(".", maxsplit=1)
        payload = _decode(encoded_payload)
        signature = _decode(encoded_signature)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidCursorError("cursor signature is invalid")
        value = json.loads(payload)
        if (
            value.get("v") != 1
            or value.get("tenant_id") != str(tenant_id)
            or isinstance(value.get("change_id"), bool)
            or not isinstance(value.get("change_id"), int)
            or value["change_id"] < 0
        ):
            raise InvalidCursorError("cursor payload is invalid")
        return cast(int, value["change_id"])
    except InvalidCursorError:
        raise
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise InvalidCursorError("cursor is malformed") from error


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
