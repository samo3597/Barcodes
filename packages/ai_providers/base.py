"""Provider-neutral AI batch interface and failure taxonomy."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from packages.contracts import AIProductResult, AIRequest


class ProviderTransientError(RuntimeError):
    """Temporary provider failure that may be retried with backoff."""


class ProviderPermanentError(RuntimeError):
    """Provider failure that cannot succeed without changing the request."""


@dataclass(frozen=True, slots=True)
class ProviderBatch:
    """Provider acknowledgement for an asynchronously submitted batch."""

    provider_batch_id: str


@dataclass(frozen=True, slots=True)
class ProviderBatchStatus:
    """Provider status plus raw per-candidate responses when complete."""

    status: Literal["submitted", "processing", "completed", "failed"]
    results: dict[str, dict[str, Any]]
    usage: dict[str, Any]


class ProductClassifier(Protocol):
    """Stable adapter contract; business services never import provider SDKs."""

    provider_name: str
    model_name: str

    async def submit_batch(self, requests: list[AIRequest]) -> ProviderBatch: ...

    async def get_batch(self, provider_batch_id: str) -> ProviderBatchStatus: ...

    async def cancel_batch(self, provider_batch_id: str) -> None: ...

    def parse_result(self, raw: dict[str, Any]) -> AIProductResult: ...
