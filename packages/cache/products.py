"""Server 2 product cache; PostgreSQL remains authoritative."""

from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from packages.contracts import PublicProduct


class ProductCache(Protocol):
    async def get(self, barcode: str) -> PublicProduct | None: ...

    async def set(self, product: PublicProduct) -> None: ...

    async def delete(self, barcode: str) -> None: ...


class RedisProductCache:
    """Short-lived current snapshots; every Redis error degrades to a miss."""

    def __init__(self, redis_url: str, ttl_seconds: int = 300) -> None:
        self.client: Redis = Redis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _key(barcode: str) -> str:
        return f"product:{barcode}:current"

    async def get(self, barcode: str) -> PublicProduct | None:
        try:
            value = await self.client.get(self._key(barcode))
        except RedisError:
            return None
        if not isinstance(value, str):
            return None
        try:
            return PublicProduct.model_validate_json(value)
        except ValueError:
            await self.delete(barcode)
            return None

    async def set(self, product: PublicProduct) -> None:
        try:
            await self.client.set(
                self._key(product.barcode),
                product.model_dump_json(),
                ex=self.ttl_seconds,
            )
        except RedisError:
            return

    async def delete(self, barcode: str) -> None:
        try:
            await self.client.delete(self._key(barcode))
        except RedisError:
            return

    async def close(self) -> None:
        await self.client.aclose()
