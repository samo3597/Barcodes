"""Tenant feedback ingestion endpoint."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from apps.public_api.auth import FeedbackWriter
from apps.public_api.dependencies import DatabaseSession
from packages.contracts import FeedbackRequest, FeedbackResponse
from packages.persistence.server2.feedback_repositories import (
    FeedbackIdempotencyConflictError,
    FeedbackProductError,
    append_feedback,
)

router = APIRouter(prefix="/v1", tags=["feedback"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_feedback(
    payload: FeedbackRequest,
    request: Request,
    principal: FeedbackWriter,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> FeedbackResponse:
    request_id = str(request.state.request_id)
    try:
        event_id, duplicate = await append_feedback(
            session,
            tenant_id=principal.tenant_id,
            api_key_id=principal.api_key_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
            feedback=payload,
        )
    except FeedbackIdempotencyConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "idempotency_conflict",
                "message": str(error),
                "retryable": False,
            },
        ) from error
    except FeedbackProductError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_feedback_product",
                "message": str(error),
                "retryable": False,
            },
        ) from error
    return FeedbackResponse(
        event_id=event_id,
        duplicate_request=duplicate,
        request_id=request_id,
    )
