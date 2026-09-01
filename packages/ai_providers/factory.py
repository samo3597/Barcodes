"""Configuration boundary for selecting an AI provider adapter."""

from packages.ai_providers.base import ProductClassifier, ProviderPermanentError
from packages.ai_providers.deterministic import DeterministicProductClassifier


def build_classifier(provider: str, environment: str) -> ProductClassifier:
    """Build an explicit adapter and prevent the development fake in production."""

    if provider == "deterministic":
        if environment == "production":
            raise ProviderPermanentError("deterministic AI provider is forbidden in production")
        return DeterministicProductClassifier()
    raise ProviderPermanentError(f"unsupported AI provider: {provider}")
