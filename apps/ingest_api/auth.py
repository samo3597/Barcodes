"""Source bearer-key authentication and scope enforcement."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.ingest_api.dependencies import DatabaseSession
from packages.domain.api_keys import extract_key_prefix, verify_source_api_key
from packages.persistence.server1.repositories import find_api_key_by_prefix

bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


@dataclass(frozen=True, slots=True)
class SourcePrincipal:
    """Authenticated source identity passed to application services."""

    source_id: UUID
    api_key_id: UUID
    scopes: frozenset[str]


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_api_key",
            "message": "Source API key is missing or invalid",
            "retryable": False,
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def authenticate_source(
    credentials: BearerCredentials,
    session: DatabaseSession,
) -> SourcePrincipal:
    """Verify the hash and return the source identity without exposing key data."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()

    prefix = extract_key_prefix(credentials.credentials)
    if prefix is None:
        raise _authentication_error()

    resolved = await find_api_key_by_prefix(session, prefix)
    if resolved is None:
        raise _authentication_error()

    api_key, source = resolved
    if api_key.status != "active" or not verify_source_api_key(
        credentials.credentials,
        api_key.key_hash,
    ):
        raise _authentication_error()
    if source.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "source_disabled",
                "message": "Source is disabled",
                "retryable": False,
            },
        )

    api_key.last_used_at = datetime.now(UTC)
    await session.commit()
    return SourcePrincipal(
        source_id=source.id,
        api_key_id=api_key.id,
        scopes=frozenset(api_key.scopes),
    )


def require_scope(scope: str) -> Callable[..., Awaitable[SourcePrincipal]]:
    """Build a dependency that authenticates a source and enforces one scope."""

    async def dependency(
        principal: Annotated[SourcePrincipal, Depends(authenticate_source)],
    ) -> SourcePrincipal:
        if scope not in principal.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "insufficient_scope",
                    "message": f"Required scope: {scope}",
                    "retryable": False,
                },
            )
        return principal

    return dependency


IngestWriter = Annotated[SourcePrincipal, Depends(require_scope("ingest:write"))]
BatchReader = Annotated[SourcePrincipal, Depends(require_scope("batches:read"))]
