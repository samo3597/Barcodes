"""Redis daily limiter behavior and outage policy."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from packages.quota import RateLimiterUnavailable, RedisDailyRateLimiter


class FakePipeline:
    def __init__(self, result: list[object] | None = None, error: Exception | None = None) -> None:
        self.result = result or [1, True]
        self.error = error

    def incr(self, _: str) -> "FakePipeline":
        return self

    def expireat(self, _: str, __: datetime) -> "FakePipeline":
        return self

    async def execute(self) -> list[object]:
        if self.error is not None:
            raise self.error
        return self.result


class FakeRedis:
    def __init__(self, pipeline: FakePipeline) -> None:
        self.value = pipeline

    def pipeline(self, *, transaction: bool) -> FakePipeline:
        assert transaction is True
        return self.value


@pytest.mark.asyncio
async def test_daily_limiter_enforces_limit_and_uses_utc_day() -> None:
    limiter = RedisDailyRateLimiter("redis://unused:6379/0")
    limiter.client = cast(Any, FakeRedis(FakePipeline([3, True])))

    result = await limiter.check(
        uuid4(),
        2,
        now=datetime(2026, 9, 1, 23, 0, tzinfo=UTC),
    )

    assert result.allowed is False
    assert result.used == 3
    assert result.reset_at == datetime(2026, 9, 2, tzinfo=UTC)


@pytest.mark.asyncio
async def test_redis_outage_is_configurable_fail_open_or_unavailable() -> None:
    error = RedisConnectionError("redis unavailable")
    open_limiter = RedisDailyRateLimiter("redis://unused:6379/0", fail_open=True)
    open_limiter.client = cast(Any, FakeRedis(FakePipeline(error=error)))
    result = await open_limiter.check(uuid4(), 100)
    assert result.allowed is True and result.degraded is True

    closed_limiter = RedisDailyRateLimiter("redis://unused:6379/0", fail_open=False)
    closed_limiter.client = cast(Any, FakeRedis(FakePipeline(error=error)))
    with pytest.raises(RateLimiterUnavailable):
        await closed_limiter.check(uuid4(), 100)
