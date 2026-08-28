"""Time-ordered identifiers used across services."""

from uuid import UUID

from uuid6 import uuid7


def new_uuid7() -> UUID:
    """Generate an RFC 9562 UUIDv7 suitable for indexed database keys."""

    return uuid7()
