"""The local provider proves the adapter can run without external credentials."""

from uuid import uuid4

import pytest

from apps.workers.pipeline import _parse_with_one_repair
from packages.ai_providers import (
    ProviderBatch,
    ProviderBatchStatus,
    ProviderPermanentError,
    build_classifier,
)
from packages.contracts import AIProductResult, AIRequest


class RepairingClassifier:
    provider_name = "repair-test"
    model_name = "repair-test-v1"

    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id

    async def submit_batch(self, requests: list[AIRequest]) -> ProviderBatch:
        assert requests[0].repair_response is not None
        return ProviderBatch(provider_batch_id="repair-1")

    async def get_batch(self, provider_batch_id: str) -> ProviderBatchStatus:
        assert provider_batch_id == "repair-1"
        return ProviderBatchStatus(
            status="completed",
            results={
                self.candidate_id: {
                    "barcode": "4850000000007",
                    "name": {"value": "Repaired", "confidence": 0.9},
                    "atg_code": {"value": "0403", "confidence": 0.9},
                    "vat": {"value": True, "confidence": 0.9},
                    "is_weighted": {"value": False, "confidence": 0.9},
                    "category_id": {"value": "dairy", "confidence": 0.9},
                    "warnings": ["schema repaired"],
                }
            },
            usage={"repair": 1},
        )

    async def cancel_batch(self, provider_batch_id: str) -> None:
        return None

    def parse_result(self, raw: dict[str, object]) -> AIProductResult:
        return AIProductResult.model_validate(raw)


@pytest.mark.asyncio
async def test_deterministic_provider_returns_parseable_structured_result() -> None:
    classifier = build_classifier("deterministic", "test")
    request = AIRequest(
        candidate_id=uuid4(),
        barcode="4850000000007",
        prompt_version="product-v1",
        input_data={
            "fields": {
                "name": "Թթվասեր",
                "atg_code": "0403",
                "vat": True,
                "is_weighted": False,
                "category": "Dairy",
            }
        },
    )

    submitted = await classifier.submit_batch([request])
    status = await classifier.get_batch(submitted.provider_batch_id)
    parsed = classifier.parse_result(status.results[str(request.candidate_id)])

    assert status.status == "completed"
    assert parsed.barcode == request.barcode
    assert parsed.category_id.value == "dairy"


def test_deterministic_provider_is_forbidden_in_production() -> None:
    with pytest.raises(ProviderPermanentError):
        build_classifier("deterministic", "production")


@pytest.mark.asyncio
async def test_invalid_schema_gets_exactly_one_repair_attempt() -> None:
    candidate_id = uuid4()
    request = AIRequest(
        candidate_id=candidate_id,
        barcode="4850000000007",
        prompt_version="product-v1",
        input_data={"fields": {}},
    )
    classifier = RepairingClassifier(str(candidate_id))

    parsed, raw, usage, error, repaired = await _parse_with_one_repair(
        classifier,
        request,
        {"vat": "not-a-contract"},
    )

    assert repaired is True
    assert error is None
    assert parsed is not None and parsed.name.value == "Repaired"
    assert raw["warnings"] == ["schema repaired"]
    assert usage == {"repair": 1}
