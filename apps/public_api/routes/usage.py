"""Tenant usage report endpoint."""

from fastapi import APIRouter, Request

from apps.public_api.auth import UsageReader
from apps.public_api.dependencies import DatabaseSession
from packages.contracts import UsageResponse, UsageSummary
from packages.persistence.server2.quota_repositories import load_usage

router = APIRouter(prefix="/v1", tags=["usage"])


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    request: Request,
    principal: UsageReader,
    session: DatabaseSession,
) -> UsageResponse:
    month, monthly_used, day, daily_used = await load_usage(
        session,
        tenant_id=principal.tenant_id,
    )
    return UsageResponse(
        data=UsageSummary(
            billing_month=month,
            monthly_unique_used=monthly_used,
            monthly_unique_limit=principal.monthly_unique_product_limit,
            usage_date=day,
            daily_request_used=daily_used,
            daily_request_limit=principal.daily_request_limit,
        ),
        request_id=str(request.state.request_id),
    )
