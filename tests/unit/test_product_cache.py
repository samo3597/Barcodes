"""Redis cache failures must not become public API failures."""

from typing import Any, cast

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from packages.cache import RedisProductCache


class UnavailableRedis:
    async def get(self, _: str) -> str | None:
        raise RedisConnectionError("redis unavailable")

    async def set(self, *_: object, **__: object) -> None:
        raise RedisConnectionError("redis unavailable")

    async def delete(self, _: str) -> None:
        raise RedisConnectionError("redis unavailable")


@pytest.mark.asyncio
async def test_redis_failure_degrades_to_cache_miss_and_noop_invalidation() -> None:
    cache = RedisProductCache("redis://unused:6379/0")
    cache.client = cast(Any, UnavailableRedis())

    assert await cache.get("4850000000007") is None
    await cache.delete("4850000000007")
