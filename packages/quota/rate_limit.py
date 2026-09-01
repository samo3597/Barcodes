"""Redis-backed daily request limiter for the Server 2 public API."""

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError


class RateLimiterUnavailable(RuntimeError):
    """Redis failed while fail-open mode was disabled."""


class DailyRateLimitResult:
    def __init__(
        self,
        *,
        allowed: bool,
        used: int | None,
        limit: int,
        reset_at: datetime,
        degraded: bool = False,
    ) -> None:
        self.allowed = allowed
        self.used = used
        self.limit = limit
        self.reset_at = reset_at
        self.degraded = degraded


class RateLimiter(Protocol):
    async def check(
        self,
        tenant_id: UUID,
        limit: int,
        *,
        now: datetime | None = None,
    ) -> DailyRateLimitResult: ...


class RedisDailyRateLimiter:
    """Count one HTTP request per tenant and UTC day in Redis."""

    def __init__(self, redis_url: str, *, fail_open: bool = True) -> None:
        self.client: Redis = Redis.from_url(redis_url, decode_responses=True)
        self.fail_open = fail_open

    @staticmethod
    def _key(tenant_id: UUID, current: datetime) -> str:
        return f"rate:tenant:{tenant_id}:{current.date().isoformat()}"

    async def check(
        self,
        tenant_id: UUID,
        limit: int,
        *,
        now: datetime | None = None,
    ) -> DailyRateLimitResult:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        reset_at = datetime.combine(
            current.date() + timedelta(days=1),
            datetime.min.time(),
            tzinfo=UTC,
        )
        try:
            pipeline = self.client.pipeline(transaction=True)
            pipeline.incr(self._key(tenant_id, current))
            pipeline.expireat(self._key(tenant_id, current), reset_at)
            values = await pipeline.execute()
            used = int(values[0])
        except RedisError as error:
            if not self.fail_open:
                raise RateLimiterUnavailable("daily request limiter is unavailable") from error
            return DailyRateLimitResult(
                allowed=True,
                used=None,
                limit=limit,
                reset_at=reset_at,
                degraded=True,
            )
        return DailyRateLimitResult(
            allowed=used <= limit,
            used=used,
            limit=limit,
            reset_at=reset_at,
        )

    async def close(self) -> None:
        await self.client.aclose()
