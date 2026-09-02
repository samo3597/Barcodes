"""Stable request, response, and error contracts shared by all services."""

from packages.contracts.ai import (
    AIBooleanValue,
    AIProductResult,
    AIRequest,
    AITextValue,
)
from packages.contracts.common import ErrorBody, ErrorEnvelope, HealthResponse
from packages.contracts.feedback import (
    ChangeItem,
    ChangesResponse,
    FeedbackFieldChange,
    FeedbackRequest,
    FeedbackResponse,
)
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
from packages.contracts.usage import MonthlyProductUsage, UsageResponse, UsageSummary

__all__ = [
    "AIBooleanValue",
    "AIProductResult",
    "AIRequest",
    "AITextValue",
    "BatchAcceptedResponse",
    "BatchStatusResponse",
    "CategoryItem",
    "CategoryListResponse",
    "ChangeItem",
    "ChangesResponse",
    "ErrorBody",
    "ErrorEnvelope",
    "FeedbackFieldChange",
    "FeedbackRequest",
    "FeedbackResponse",
    "HealthResponse",
    "IngestBatchItem",
    "IngestBatchRequest",
    "MonthlyProductUsage",
    "ProductBatchItem",
    "ProductBatchRequest",
    "ProductBatchResponse",
    "ProductResponse",
    "ProductUpsertedEvent",
    "PublicationApplyResponse",
    "PublicProduct",
    "UsageResponse",
    "UsageSummary",
]
