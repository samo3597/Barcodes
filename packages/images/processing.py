"""SSRF-aware image download, normalization, and local object storage."""

import asyncio
import hashlib
import io
import ipaddress
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_REDIRECTS = 4
MAX_DIMENSION = 2_048


class ImagePolicyError(ValueError):
    """The remote resource violates a security or image policy."""


@dataclass(frozen=True, slots=True)
class DownloadedImage:
    content: bytes
    content_hash: str
    width: int
    height: int


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def validate_public_url(url: str) -> str:
    """Resolve a URL and reject credentials, local names, and non-public addresses."""

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImagePolicyError("image URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ImagePolicyError("image URL must not contain credentials")
    if parsed.hostname.lower() == "localhost":
        raise ImagePolicyError("local image hosts are forbidden")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise ImagePolicyError("image host cannot be resolved") from error
    resolved = {str(entry[4][0]) for entry in addresses}
    if not resolved or any(not _is_public(address) for address in resolved):
        raise ImagePolicyError("image host resolves to a non-public address")
    return url


def normalize_to_webp(raw: bytes) -> DownloadedImage:
    """Decode once, bound decompression, resize, and emit metadata-free WebP."""

    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ImagePolicyError("image size is outside the allowed range")
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.seek(0)
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ImagePolicyError("decoded image exceeds the pixel limit")
            source.load()
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ImagePolicyError("resource is not a supported image") from error
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=85, method=6, exif=b"", icc_profile=None)
    content = output.getvalue()
    return DownloadedImage(
        content=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        width=image.width,
        height=image.height,
    )


async def download_image(url: str, *, timeout_seconds: float = 10.0) -> DownloadedImage:
    """Validate every redirect target and stream at most 10 MiB."""

    current = url
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await validate_public_url(current)
            async with client.stream("GET", current, headers={"Accept": "image/*"}) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ImagePolicyError("redirect has no location")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        declared_size = int(declared)
                    except ValueError as error:
                        raise ImagePolicyError("invalid image content length") from error
                    if declared_size > MAX_IMAGE_BYTES:
                        raise ImagePolicyError("image exceeds the 10 MiB limit")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_IMAGE_BYTES:
                        raise ImagePolicyError("image exceeds the 10 MiB limit")
                return normalize_to_webp(bytes(content))
    raise ImagePolicyError("too many image redirects")


class LocalImageStorage:
    """Development adapter with the same content-addressed keys as object storage."""

    def __init__(self, root: Path, public_base_url: str) -> None:
        self.root = root
        self.public_base_url = public_base_url.rstrip("/")

    def put(self, image: DownloadedImage) -> tuple[str, str]:
        key = f"images/{image.content_hash[:2]}/{image.content_hash}.webp"
        destination = self.root / Path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(image.content)
        return key, f"{self.public_base_url}/{key}"
