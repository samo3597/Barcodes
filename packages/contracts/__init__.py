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
from packages.contracts.internal import ProductUpsertedEvent, PublicationApplyResponse
from packages.contracts.product import (
    CategoryItem,
    CategoryListResponse,
    ProductBatchItem,
    ProductBatchRequest,
    ProductBatchResponse,
    ProductResponse,
    PublicProduct,
)

__all__ = [
    "AIBooleanValue",
    "AIProductResult",
    "AIRequest",
    "AITextValue",
    "BatchAcceptedResponse",
    "BatchStatusResponse",
    "CategoryItem",
    "CategoryListResponse",
    "ErrorBody",
    "ErrorEnvelope",
    "HealthResponse",
    "IngestBatchItem",
    "IngestBatchRequest",
    "ProductBatchItem",
    "ProductBatchRequest",
    "ProductBatchResponse",
    "ProductResponse",
    "ProductUpsertedEvent",
    "PublicationApplyResponse",
    "PublicProduct",
]
