"""Tenant-facing incremental product change feed."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status

from apps.public_api.auth import ChangesReader
from apps.public_api.dependencies import DatabaseSession
from packages.contracts import ChangeItem, ChangesResponse
from packages.domain.change_cursor import (
    InvalidCursorError,
    decode_change_cursor,
    encode_change_cursor,
)
from packages.persistence.server2.change_repositories import CursorExpiredError, load_tenant_changes
from packages.persistence.server2.repositories import product_contract

router = APIRouter(prefix="/v1", tags=["changes"])


@router.get("/changes", response_model=ChangesResponse, response_model_exclude_none=True)
async def get_changes(
    request: Request,
    principal: ChangesReader,
    session: DatabaseSession,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int | None = Query(default=None, ge=1),
    include: Literal["data"] | None = None,
) -> ChangesResponse:
    page_limit = limit or request.app.state.changes_default_limit
    if page_limit > request.app.state.changes_max_limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_changes_limit",
                "message": f"limit must not exceed {request.app.state.changes_max_limit}",
                "retryable": False,
            },
        )
    try:
        after_id = (
            decode_change_cursor(
                cursor, principal.tenant_id, request.app.state.cursor_signing_secret
            )
            if cursor
            else 0
        )
    except InvalidCursorError as error:
        previous_secret = request.app.state.cursor_previous_signing_secret
        try:
            if not previous_secret or not cursor:
                raise error
            after_id = decode_change_cursor(cursor, principal.tenant_id, previous_secret)
        except InvalidCursorError as previous_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_cursor",
                    "message": str(previous_error),
                    "retryable": False,
                },
            ) from previous_error

    retained_since = datetime.now(UTC) - timedelta(days=request.app.state.changes_retention_days)
    try:
        rows, has_more, products = await load_tenant_changes(
            session,
            tenant_id=principal.tenant_id,
            after_change_id=after_id,
            limit=page_limit,
            retained_since=retained_since,
            include_data=include == "data",
        )
    except CursorExpiredError as error:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": "cursor_expired", "message": str(error), "retryable": False},
        ) from error

    next_id = rows[-1].change_id if rows else after_id
    return ChangesResponse(
        changes=[
            ChangeItem(
                change_id=row.change_id,
                type=row.change_type,
                barcode=row.barcode,
                version=row.version,
                changed_at=row.changed_at,
                data=(product_contract(products[row.barcode]) if row.barcode in products else None),
            )
            for row in rows
        ],
        next_cursor=encode_change_cursor(
            next_id, principal.tenant_id, request.app.state.cursor_signing_secret
        ),
        has_more=has_more,
        request_id=str(request.state.request_id),
    )
