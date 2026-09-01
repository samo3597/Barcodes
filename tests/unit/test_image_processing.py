"""Security and normalization checks for untrusted source images."""

import asyncio
import io

import pytest
from PIL import Image, PngImagePlugin

from packages.images import ImagePolicyError, normalize_to_webp, validate_public_url


def test_private_image_host_is_rejected() -> None:
    with pytest.raises(ImagePolicyError, match="non-public"):
        asyncio.run(validate_public_url("http://127.0.0.1/internal.png"))


def test_normalization_emits_bounded_metadata_free_webp() -> None:
    source = Image.new("RGB", (3_000, 1_500), "red")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "must disappear")
    raw = io.BytesIO()
    source.save(raw, format="PNG", pnginfo=metadata)

    normalized = normalize_to_webp(raw.getvalue())

    assert normalized.width == 2_048
    assert normalized.height == 1_024
    with Image.open(io.BytesIO(normalized.content)) as result:
        assert result.format == "WEBP"
        assert "Comment" not in result.info


def test_oversized_payload_is_rejected_before_decode() -> None:
    with pytest.raises(ImagePolicyError, match="size"):
        normalize_to_webp(b"x" * (10 * 1024 * 1024 + 1))
