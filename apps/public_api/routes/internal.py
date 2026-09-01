"""Protected Server 1 to Server 2 publication endpoint."""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from apps.public_api.dependencies import DatabaseSession, ProductCacheDependency
from apps.public_api.internal_auth import verify_internal_signature
from apps.public_api.services import receive_publication
from packages.contracts import ProductUpsertedEvent, PublicationApplyResponse
from packages.persistence.server2.repositories import VersionConflictError

router = APIRouter(prefix="/internal/v1", tags=["internal publication"])


@router.put("/products/{barcode}", response_model=PublicationApplyResponse)
async def put_product(
    barcode: str,
    event: ProductUpsertedEvent,
    request: Request,
    session: DatabaseSession,
    cache: ProductCacheDependency,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    signature_timestamp: str = Header(alias="X-Signature-Timestamp"),
    signature: str = Header(alias="X-Signature-SHA256"),
    x_event_id: str | None = Header(default=None, alias="X-Event-Id"),
) -> PublicationApplyResponse:
    try:
        header_event_id = UUID(idempotency_key)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_idempotency_key",
                "message": "Idempotency-Key must be the event UUID",
                "retryable": False,
            },
        ) from error
    if (
        header_event_id != event.event_id
        or (x_event_id is not None and x_event_id != str(event.event_id))
        or barcode != event.aggregate_id
        or barcode != event.payload.barcode
        or event.aggregate_version != event.payload.version
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "publication_identity_conflict",
                "message": "Path, headers, envelope, and product identity must match",
                "retryable": False,
            },
        )
    verify_internal_signature(
        body=await request.body(),
        event_id=event.event_id,
        timestamp=signature_timestamp,
        signature=signature,
        secret=request.app.state.internal_sync_secret,
        replay_window_seconds=request.app.state.internal_replay_window_seconds,
    )
    try:
        return await receive_publication(session, cache, event)
    except VersionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "product_version_conflict",
                "message": str(error),
                "retryable": False,
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_publication_event",
                "message": str(error),
                "retryable": False,
            },
        ) from error
