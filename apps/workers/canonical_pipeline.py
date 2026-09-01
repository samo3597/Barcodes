"""Canonical publication and non-blocking image lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.contracts import AIProductResult
from packages.domain.canonical import CanonicalFields
from packages.images import ImagePolicyError, LocalImageStorage, download_image
from packages.persistence.server1.canonical_repositories import (
    create_image_fetch,
    create_product_version,
    upsert_image_asset,
)
from packages.persistence.server1.models import AIResult, ImageAsset, ImageFetch, ProductCandidate


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    version: int
    created: bool
    image_fetch_id: UUID | None


def _source_image_url(candidate: ProductCandidate) -> str | None:
    fields = candidate.normalized_payload.get("fields")
    if not isinstance(fields, dict):
        return None
    value = fields.get("image_url")
    return value.strip() if isinstance(value, str) and value.strip() else None


async def canonicalize_ai_result(
    session: AsyncSession,
    result_id: UUID,
    *,
    image_asset_id: UUID | None = None,
) -> CanonicalizationResult:
    """Publish valid AI text immediately and optionally attach a secured image."""

    row = await session.execute(
        select(AIResult, ProductCandidate)
        .join(ProductCandidate, ProductCandidate.id == AIResult.candidate_id)
        .where(AIResult.id == result_id)
    )
    pair = row.one_or_none()
    if pair is None:
        raise ValueError(f"unknown AI result: {result_id}")
    result, candidate = pair
    if result.status != "valid" or result.parsed_result is None:
        raise ValueError("only valid AI results can become canonical products")
    parsed = AIProductResult.model_validate(result.parsed_result)
    asset = await session.get(ImageAsset, image_asset_id) if image_asset_id else None
    fields = CanonicalFields(
        barcode=parsed.barcode,
        name=parsed.name.value,
        image_url=asset.public_url if asset is not None else None,
        atg_code=parsed.atg_code.value,
        vat=parsed.vat.value,
        is_weighted=parsed.is_weighted.value,
        category_id=parsed.category_id.value,
        quality_status="ai_processed",
    )
    version, event = await create_product_version(
        session,
        fields,
        origin="ai_run",
        origin_id=result.id,
        image_asset_id=asset.id if asset is not None else None,
    )
    fetch_id = None
    source_url = _source_image_url(candidate)
    if source_url is not None and asset is None:
        fetch_id = await create_image_fetch(session, result.id, source_url)
    await session.commit()
    return CanonicalizationResult(version.version, event is not None, fetch_id)


async def canonicalize_job_results(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
) -> list[UUID]:
    """Canonicalize all valid results and return image work to enqueue."""

    async with session_factory() as session:
        result_ids = list(
            await session.scalars(
                select(AIResult.id).where(AIResult.job_id == job_id, AIResult.status == "valid")
            )
        )
    fetch_ids: list[UUID] = []
    for result_id in result_ids:
        async with session_factory() as session:
            outcome = await canonicalize_ai_result(session, result_id)
            if outcome.image_fetch_id is not None:
                fetch_ids.append(outcome.image_fetch_id)
    return fetch_ids


async def process_image_fetch(
    session_factory: async_sessionmaker[AsyncSession],
    fetch_id: UUID,
    *,
    storage_root: Path,
    public_base_url: str,
) -> None:
    """Secure, normalize, store, then create an image-bearing product version."""

    async with session_factory() as session:
        fetch = await session.get(ImageFetch, fetch_id)
        if fetch is None:
            raise ValueError(f"unknown image fetch: {fetch_id}")
        if fetch.status == "completed":
            return
        fetch.status = "processing"
        fetch.attempts += 1
        await session.commit()
        source_url = fetch.source_url
        result_id = fetch.ai_result_id
    try:
        image = await download_image(source_url)
        storage_key, public_url = LocalImageStorage(storage_root, public_base_url).put(image)
        async with session_factory() as session:
            asset = await upsert_image_asset(
                session,
                content_hash=image.content_hash,
                storage_key=storage_key,
                public_url=public_url,
                size_bytes=len(image.content),
                width=image.width,
                height=image.height,
            )
            fetch = await session.get(ImageFetch, fetch_id)
            if fetch is None:
                raise RuntimeError("image fetch disappeared during processing")
            fetch.status = "completed"
            fetch.image_asset_id = asset.id
            fetch.completed_at = datetime.now(UTC)
            fetch.error_code = None
            fetch.error_message = None
            await session.commit()
            asset_id = asset.id
        async with session_factory() as session:
            await canonicalize_ai_result(session, result_id, image_asset_id=asset_id)
    except (ImagePolicyError, httpx.HTTPError, OSError, ValidationError) as error:
        async with session_factory() as session:
            fetch = await session.get(ImageFetch, fetch_id)
            if fetch is not None:
                fetch.status = "failed"
                fetch.error_code = type(error).__name__
                fetch.error_message = str(error)[:2_000]
                fetch.completed_at = datetime.now(UTC)
                await session.commit()
