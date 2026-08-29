"""Local deterministic classifier used only for development and tests."""

import re
from typing import Any

from packages.ai_providers.base import (
    ProductClassifier,
    ProviderBatch,
    ProviderBatchStatus,
    ProviderPermanentError,
)
from packages.contracts import AIProductResult, AIRequest
from packages.domain.identifiers import new_uuid7


def _slug(value: object) -> str:
    candidate = re.sub(r"[^a-z0-9]+", ".", str(value).lower()).strip(".")
    return candidate[:100] or "uncategorized"


class DeterministicProductClassifier(ProductClassifier):
    """Predictable adapter that makes the pipeline testable without paid API access."""

    provider_name = "deterministic"
    model_name = "deterministic-v1"

    def __init__(self) -> None:
        self._batches: dict[str, ProviderBatchStatus] = {}

    async def submit_batch(self, requests: list[AIRequest]) -> ProviderBatch:
        provider_batch_id = f"local_{new_uuid7()}"
        results = {str(request.candidate_id): self._classify(request) for request in requests}
        self._batches[provider_batch_id] = ProviderBatchStatus(
            status="completed",
            results=results,
            usage={"input_items": len(requests), "estimated_cost": 0},
        )
        return ProviderBatch(provider_batch_id=provider_batch_id)

    async def get_batch(self, provider_batch_id: str) -> ProviderBatchStatus:
        try:
            return self._batches[provider_batch_id]
        except KeyError as error:
            raise ProviderPermanentError("unknown deterministic provider batch") from error

    async def cancel_batch(self, provider_batch_id: str) -> None:
        self._batches.pop(provider_batch_id, None)

    def parse_result(self, raw: dict[str, Any]) -> AIProductResult:
        return AIProductResult.model_validate(raw)

    def _classify(self, request: AIRequest) -> dict[str, Any]:
        fields = request.input_data.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}
        warnings: list[str] = ["deterministic development adapter; not a semantic AI result"]

        def value_or_default(field: str, default: object) -> tuple[object, float]:
            value = fields.get(field)
            if value is None or value == "":
                warnings.append(f"{field} defaulted")
                return default, 0.1
            return value, 1.0

        name, name_confidence = value_or_default("name", f"Unknown product {request.barcode}")
        atg_code, atg_confidence = value_or_default("atg_code", "0000")
        vat, vat_confidence = value_or_default("vat", False)
        is_weighted, weighted_confidence = value_or_default("is_weighted", False)
        raw_category, category_confidence = value_or_default("category", "uncategorized")
        return {
            "barcode": request.barcode,
            "name": {"value": str(name), "confidence": name_confidence},
            "atg_code": {"value": str(atg_code), "confidence": atg_confidence},
            "vat": {"value": vat, "confidence": vat_confidence},
            "is_weighted": {"value": is_weighted, "confidence": weighted_confidence},
            "category_id": {"value": _slug(raw_category), "confidence": category_confidence},
            "warnings": warnings,
        }
