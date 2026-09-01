"""Tests for deterministic pre-AI source merging."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from packages.domain.candidates import SourceRevisionInput, build_candidate


def revision(
    *,
    name: str,
    priority: int,
    occurred_at: datetime,
) -> SourceRevisionInput:
    return SourceRevisionInput(
        revision_id=uuid4(),
        source_id=uuid4(),
        barcode="4850000000007",
        payload={"name": name, "vat": True, "category": "Dairy"},
        field_priorities={"name": priority},
        occurred_at=occurred_at,
    )


def test_priority_wins_over_freshness_and_merge_is_order_independent() -> None:
    now = datetime.now(UTC)
    trusted = revision(name="Trusted name", priority=10, occurred_at=now - timedelta(days=2))
    recent = revision(name="Recent name", priority=100, occurred_at=now)

    first = build_candidate("4850000000007", [recent, trusted])
    second = build_candidate("4850000000007", [trusted, recent])

    assert first.normalized_payload["fields"]["name"] == "Trusted name"
    assert first.input_hash == second.input_hash
    assert first.source_revision_ids == second.source_revision_ids


def test_newest_value_wins_when_source_priorities_are_equal() -> None:
    now = datetime.now(UTC)
    older = revision(name="Older", priority=50, occurred_at=now - timedelta(hours=1))
    newer = revision(name="Newer", priority=50, occurred_at=now)

    candidate = build_candidate("4850000000007", [older, newer])

    assert candidate.normalized_payload["fields"]["name"] == "Newer"
