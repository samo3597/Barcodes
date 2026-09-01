"""Tenant bearer-key authentication and scope enforcement."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.public_api.dependencies import DatabaseSession
from packages.domain.api_keys import extract_tenant_key_prefix, verify_tenant_api_key
from packages.persistence.server2.repositories import find_tenant_key_by_prefix

bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    tenant_id: UUID
    api_key_id: UUID
    scopes: frozenset[str]


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_api_key",
            "message": "Tenant API key is missing or invalid",
            "retryable": False,
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def authenticate_tenant(
    credentials: BearerCredentials,
    session: DatabaseSession,
) -> TenantPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()
    prefix = extract_tenant_key_prefix(credentials.credentials)
    if prefix is None:
        raise _authentication_error()
    resolved = await find_tenant_key_by_prefix(session, prefix)
    if resolved is None:
        raise _authentication_error()
    api_key, tenant = resolved
    if api_key.status != "active" or not verify_tenant_api_key(
        credentials.credentials, api_key.key_hash
    ):
        raise _authentication_error()
    if tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "tenant_disabled",
                "message": "Tenant is disabled",
                "retryable": False,
            },
        )
    api_key.last_used_at = datetime.now(UTC)
    await session.commit()
    return TenantPrincipal(tenant.id, api_key.id, frozenset(api_key.scopes))


def require_scope(scope: str) -> Callable[..., Awaitable[TenantPrincipal]]:
    async def dependency(
        principal: Annotated[TenantPrincipal, Depends(authenticate_tenant)],
    ) -> TenantPrincipal:
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


ProductReader = Annotated[TenantPrincipal, Depends(require_scope("products:read"))]
CategoryReader = Annotated[TenantPrincipal, Depends(require_scope("categories:read"))]
