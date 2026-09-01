"""Tenant quota and usage response contracts."""

from datetime import date

from pydantic import Field

from packages.contracts.common import StrictContract


class MonthlyProductUsage(StrictContract):
    monthly_unique_used: int = Field(ge=0)
    monthly_unique_limit: int = Field(ge=0)


class UsageSummary(MonthlyProductUsage):
    billing_month: date
    daily_request_used: int = Field(ge=0)
    daily_request_limit: int = Field(ge=0)
    usage_date: date


class UsageResponse(StrictContract):
    data: UsageSummary
    request_id: str
