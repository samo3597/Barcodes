"""Source batch acceptance and status endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status

from apps.ingest_api.auth import BatchReader, IngestWriter
from apps.ingest_api.dependencies import DatabaseSession
from apps.ingest_api.services import (
    BatchNotFoundError,
    IdempotencyConflictError,
    accept_batch,
    get_batch,
)
from packages.contracts import BatchAcceptedResponse, BatchStatusResponse, IngestBatchRequest

router = APIRouter(prefix="/ingest/v1/batches", tags=["ingest batches"])
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]


@router.post("", response_model=BatchAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_batch(
    payload: IngestBatchRequest,
    idempotency_key: IdempotencyKey,
    principal: IngestWriter,
    session: DatabaseSession,
) -> BatchAcceptedResponse:
    try:
        accepted = await accept_batch(
            session,
            principal.source_id,
            idempotency_key,
            payload,
        )
    except IdempotencyConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "idempotency_conflict",
                "message": "Idempotency-Key was already used with a different payload",
                "retryable": False,
            },
        ) from error

    return BatchAcceptedResponse(
        batch_id=accepted.batch.id,
        status=accepted.batch.status,
        received_items=accepted.batch.received,
        duplicate_request=accepted.duplicate_request,
    )


@router.get("/{batch_id}", response_model=BatchStatusResponse)
async def batch_status(
    batch_id: UUID,
    principal: BatchReader,
    session: DatabaseSession,
) -> BatchStatusResponse:
    try:
        batch = await get_batch(session, principal.source_id, batch_id)
    except BatchNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "batch_not_found",
                "message": "Batch does not exist in this source scope",
                "retryable": False,
            },
        ) from error

    return BatchStatusResponse(
        batch_id=batch.id,
        status=batch.status,
        received=batch.received,
        validated=batch.validated,
        rejected=batch.rejected,
        ai_pending=batch.ai_pending,
        published=batch.published,
        failed=batch.failed,
    )
