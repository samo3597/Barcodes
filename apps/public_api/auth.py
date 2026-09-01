"""Tenant bearer-key authentication and scope enforcement."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.public_api.dependencies import DatabaseSession, RateLimiterDependency
from packages.domain.api_keys import extract_tenant_key_prefix, verify_tenant_api_key
from packages.persistence.server2.quota_repositories import record_daily_request
from packages.persistence.server2.repositories import find_tenant_key_by_prefix
from packages.quota import RateLimiterUnavailable

bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    tenant_id: UUID
    api_key_id: UUID
    scopes: frozenset[str]
    daily_request_limit: int
    monthly_unique_product_limit: int


def _plan_limit(plan: dict[str, object], key: str, default: int) -> int:
    value = plan.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return default
    return value


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
    request: Request,
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
    return TenantPrincipal(
        tenant.id,
        api_key.id,
        frozenset(api_key.scopes),
        _plan_limit(
            tenant.plan_config,
            "daily_request_limit",
            request.app.state.default_daily_request_limit,
        ),
        _plan_limit(
            tenant.plan_config,
            "monthly_unique_product_limit",
            request.app.state.default_monthly_unique_product_limit,
        ),
    )


def require_scope(scope: str) -> Callable[..., Awaitable[TenantPrincipal]]:
    async def dependency(
        request: Request,
        response: Response,
        session: DatabaseSession,
        limiter: RateLimiterDependency,
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
        try:
            result = await limiter.check(principal.tenant_id, principal.daily_request_limit)
        except RateLimiterUnavailable as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "rate_limiter_unavailable",
                    "message": "Daily request limiter is unavailable",
                    "retryable": True,
                },
            ) from error
        await record_daily_request(
            session,
            tenant_id=principal.tenant_id,
            limited=not result.allowed,
        )
        if result.used is not None:
            remaining = max(0, result.limit - result.used)
            rate_headers = {
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(result.reset_at.timestamp())),
            }
            request.state.rate_limit_headers = rate_headers
            response.headers.update(rate_headers)
        if not result.allowed:
            retry_after = max(1, int((result.reset_at - datetime.now(UTC)).total_seconds()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "daily_request_limit",
                    "message": "Daily request limit reached",
                    "details": {"limit": result.limit, "used": result.used},
                    "retryable": True,
                },
                headers={"Retry-After": str(retry_after)},
            )
        return principal

    return dependency


ProductReader = Annotated[TenantPrincipal, Depends(require_scope("products:read"))]
CategoryReader = Annotated[TenantPrincipal, Depends(require_scope("categories:read"))]
UsageReader = Annotated[TenantPrincipal, Depends(require_scope("usage:read"))]
