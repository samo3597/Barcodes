"""Tenant-facing product and category reads."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from apps.public_api.auth import CategoryReader, ProductReader
from apps.public_api.dependencies import DatabaseSession, ProductCacheDependency
from apps.public_api.services import get_public_product, get_public_products
from packages.contracts import (
    CategoryItem,
    CategoryListResponse,
    MonthlyProductUsage,
    ProductBatchItem,
    ProductBatchRequest,
    ProductBatchResponse,
    ProductResponse,
)
from packages.domain.ingest import normalize_barcode
from packages.persistence.server2.quota_repositories import reserve_monthly_products
from packages.persistence.server2.repositories import list_active_categories

router = APIRouter(prefix="/v1", tags=["public products"])


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _validated_barcode(value: str) -> str:
    try:
        return normalize_barcode(value)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_barcode",
                "message": str(error),
                "retryable": False,
            },
        ) from error


@router.get("/products/{barcode}", response_model=ProductResponse)
async def get_product(
    barcode: str,
    request: Request,
    response: Response,
    principal: ProductReader,
    session: DatabaseSession,
    cache: ProductCacheDependency,
) -> ProductResponse | Response:
    normalized = _validated_barcode(barcode)
    product = await get_public_product(session, cache, normalized)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "product_not_found",
                "message": "Product was not found",
                "retryable": False,
            },
        )
    allowed, used = await reserve_monthly_products(
        session,
        tenant_id=principal.tenant_id,
        api_key_id=principal.api_key_id,
        barcodes=[normalized],
        limit=principal.monthly_unique_product_limit,
    )
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "monthly_unique_product_limit",
                "message": "Monthly unique product limit reached",
                "details": {
                    "limit": principal.monthly_unique_product_limit,
                    "used": used,
                },
                "retryable": False,
            },
        )
    etag = f'"{product.barcode}:{product.version}"'
    if request.headers.get("If-None-Match") == etag:
        headers = dict(getattr(request.state, "rate_limit_headers", {}))
        headers["ETag"] = etag
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=300"
    return ProductResponse(data=product, request_id=_request_id(request))


@router.post("/products/batch", response_model=ProductBatchResponse)
async def get_product_batch(
    payload: ProductBatchRequest,
    request: Request,
    principal: ProductReader,
    session: DatabaseSession,
    cache: ProductCacheDependency,
) -> ProductBatchResponse:
    products = await get_public_products(session, cache, payload.barcodes)
    existing_in_order = [
        barcode for barcode in dict.fromkeys(payload.barcodes) if barcode in products
    ]
    allowed, used = await reserve_monthly_products(
        session,
        tenant_id=principal.tenant_id,
        api_key_id=principal.api_key_id,
        barcodes=existing_in_order,
        limit=principal.monthly_unique_product_limit,
    )
    results = [
        ProductBatchItem(
            barcode=barcode,
            status=(
                "not_found"
                if barcode not in products
                else "ok"
                if barcode in allowed
                else "quota_exceeded"
            ),
            data=products.get(barcode) if barcode in allowed else None,
            error=(
                None
                if barcode in allowed
                else "product_not_found"
                if barcode not in products
                else "monthly_unique_product_limit"
            ),
        )
        for barcode in payload.barcodes
    ]
    return ProductBatchResponse(
        results=results,
        usage=MonthlyProductUsage(
            monthly_unique_used=used,
            monthly_unique_limit=principal.monthly_unique_product_limit,
        ),
        request_id=_request_id(request),
    )


@router.get("/categories", response_model=CategoryListResponse)
async def get_categories(
    request: Request,
    _: CategoryReader,
    session: DatabaseSession,
) -> CategoryListResponse:
    categories = await list_active_categories(session)
    return CategoryListResponse(
        data=[
            CategoryItem(
                category_id=item.category_id,
                name=item.name,
                parent_id=item.parent_id,
            )
            for item in categories
        ],
        request_id=_request_id(request),
    )
