"""Deterministic source-merging rules used before any AI call."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from packages.domain.ingest import canonical_payload_hash, normalize_barcode

CANDIDATE_FIELDS = (
    "name",
    "image_url",
    "atg_code",
    "vat",
    "is_weighted",
    "category",
)
DEFAULT_FIELD_PRIORITY = 1_000


@dataclass(frozen=True, slots=True)
class SourceRevisionInput:
    """Minimal immutable source revision needed by the merge algorithm."""

    revision_id: UUID
    source_id: UUID
    barcode: str
    payload: dict[str, Any]
    field_priorities: dict[str, Any]
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """Normalized AI input whose hash changes only when its semantics change."""

    barcode: str
    input_hash: str
    normalized_payload: dict[str, Any]
    source_revision_ids: tuple[UUID, ...]


def _priority(revision: SourceRevisionInput, field: str) -> int:
    value = revision.field_priorities.get(field, DEFAULT_FIELD_PRIORITY)
    return (
        value if isinstance(value, int) and not isinstance(value, bool) else DEFAULT_FIELD_PRIORITY
    )


def _has_value(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def build_candidate(barcode: str, revisions: list[SourceRevisionInput]) -> CandidateSnapshot:
    """Choose every field by priority, freshness, then stable source/revision IDs."""

    normalized_barcode = normalize_barcode(barcode)
    applicable = [revision for revision in revisions if revision.barcode == normalized_barcode]
    if not applicable:
        raise ValueError("at least one matching source revision is required")

    fields: dict[str, Any] = {}
    origins: dict[str, dict[str, str]] = {}
    for field in CANDIDATE_FIELDS:
        choices = [revision for revision in applicable if _has_value(revision.payload.get(field))]
        if not choices:
            fields[field] = None
            continue
        selected = min(
            choices,
            key=lambda revision: (
                _priority(revision, field),
                -revision.occurred_at.timestamp(),
                str(revision.source_id),
                str(revision.revision_id),
            ),
        )
        fields[field] = selected.payload[field]
        origins[field] = {
            "source_id": str(selected.source_id),
            "revision_id": str(selected.revision_id),
        }

    revision_ids = tuple(sorted((revision.revision_id for revision in applicable), key=str))
    normalized_payload: dict[str, Any] = {
        "barcode": normalized_barcode,
        "fields": fields,
        "origins": origins,
        "source_revision_ids": [str(revision_id) for revision_id in revision_ids],
        "source_count": len({revision.source_id for revision in applicable}),
    }
    return CandidateSnapshot(
        barcode=normalized_barcode,
        input_hash=canonical_payload_hash(normalized_payload),
        normalized_payload=normalized_payload,
        source_revision_ids=revision_ids,
    )
