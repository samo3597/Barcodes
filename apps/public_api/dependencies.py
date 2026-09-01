"""FastAPI dependencies for Server 2 sessions and cache."""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.cache import ProductCache


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_product_cache(request: Request) -> ProductCache:
    return cast(ProductCache, request.app.state.product_cache)


DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
ProductCacheDependency = Annotated[ProductCache, Depends(get_product_cache)]
