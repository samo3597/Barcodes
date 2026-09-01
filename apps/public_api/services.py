"""Cache-aside public reads and internal publication orchestration."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from packages.cache import ProductCache
from packages.contracts import ProductUpsertedEvent, PublicationApplyResponse, PublicProduct
from packages.persistence.server2.repositories import (
    apply_publication_event,
    load_product,
    load_products,
)


async def get_public_product(
    session: AsyncSession,
    cache: ProductCache,
    barcode: str,
) -> PublicProduct | None:
    cached = await cache.get(barcode)
    if cached is not None:
        return cached
    product = await load_product(session, barcode)
    if product is not None:
        await cache.set(product)
    return product


async def get_public_products(
    session: AsyncSession,
    cache: ProductCache,
    barcodes: Sequence[str],
) -> dict[str, PublicProduct]:
    unique = list(dict.fromkeys(barcodes))
    products: dict[str, PublicProduct] = {}
    missing: list[str] = []
    for barcode in unique:
        cached = await cache.get(barcode)
        if cached is None:
            missing.append(barcode)
        else:
            products[barcode] = cached
    database_products = await load_products(session, missing)
    products.update(database_products)
    for product in database_products.values():
        await cache.set(product)
    return products


async def receive_publication(
    session: AsyncSession,
    cache: ProductCache,
    event: ProductUpsertedEvent,
) -> PublicationApplyResponse:
    response, applied_now = await apply_publication_event(session, event)
    if applied_now:
        await cache.delete(event.aggregate_id)
    return response
