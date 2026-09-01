"""Canonical version equality and audit-diff rules."""

from packages.domain.canonical import CanonicalFields, canonical_hash, changed_fields


def fields(*, name: str = "Milk", image_url: str | None = None) -> CanonicalFields:
    return CanonicalFields(
        barcode="4850000000007",
        name=name,
        image_url=image_url,
        atg_code="0401",
        vat=True,
        is_weighted=False,
        category_id="dairy",
        quality_status="ai_processed",
    )


def test_hash_is_deterministic_and_changes_with_public_data() -> None:
    assert canonical_hash(fields()) == canonical_hash(fields())
    assert canonical_hash(fields()) != canonical_hash(fields(name="Cream"))


def test_changed_fields_contains_only_semantic_delta() -> None:
    previous = fields().model_dump(mode="json")
    current = fields(image_url="https://cdn.example/images/a.webp").model_dump(mode="json")

    assert changed_fields(previous, current) == {
        "image_url": {"old": None, "new": "https://cdn.example/images/a.webp"}
    }
