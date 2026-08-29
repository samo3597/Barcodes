"""Stable request, response, and error contracts shared by all services."""

from packages.contracts.ai import (
    AIBooleanValue,
    AIProductResult,
    AIRequest,
    AITextValue,
)
from packages.contracts.common import ErrorBody, ErrorEnvelope, HealthResponse
from packages.contracts.ingest import (
    BatchAcceptedResponse,
    BatchStatusResponse,
    IngestBatchItem,
    IngestBatchRequest,
)

__all__ = [
    "AIBooleanValue",
    "AIProductResult",
    "AIRequest",
    "AITextValue",
    "BatchAcceptedResponse",
    "BatchStatusResponse",
    "ErrorBody",
    "ErrorEnvelope",
    "HealthResponse",
    "IngestBatchItem",
    "IngestBatchRequest",
]
