"""Security and normalization checks for untrusted source images."""

import asyncio
import io
import socket

import httpx
import pytest
from PIL import Image, PngImagePlugin

from packages.images import ImagePolicyError, normalize_to_webp, validate_public_url
from packages.images.processing import download_image


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


def test_unsupported_image_format_is_rejected() -> None:
    raw = io.BytesIO()
    Image.new("RGB", (10, 10)).save(raw, format="GIF")
    with pytest.raises(ImagePolicyError):
        normalize_to_webp(raw.getvalue())


@pytest.mark.asyncio
async def test_redirect_to_private_ip_is_blocked_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (a[0] if a[0] == "127.0.0.1" else "8.8.8.8", 80),
            )
        ],
    )
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/metadata"})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: client_type(transport=httpx.MockTransport(respond), **kw)
    )
    with pytest.raises(ImagePolicyError, match="non-public"):
        await download_image("https://public.example/image")
    assert seen == ["https://public.example/image"]


@pytest.mark.asyncio
async def test_redirect_budget_is_three(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": f"/redirect/{len(seen)}"})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: client_type(transport=httpx.MockTransport(respond), **kw)
    )
    with pytest.raises(ImagePolicyError, match="too many"):
        await download_image("https://public.example/image")
    assert len(seen) == 4  # initial request plus three redirects, no fifth request
