"""Creation and verification of source API keys."""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LENGTH = 32


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    """The secret is returned once; only the prefix and hash are persisted."""

    raw_key: str
    prefix: str
    encoded_hash: str


def _derive(raw_key: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        raw_key.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_LENGTH,
    )


def _generate_api_key(kind: str) -> GeneratedApiKey:
    prefix = secrets.token_hex(6)
    raw_key = f"{kind}_{prefix}_{secrets.token_urlsafe(32)}"
    salt = secrets.token_bytes(16)
    digest = _derive(raw_key, salt)
    encoded_hash = "$".join(
        (
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )
    return GeneratedApiKey(raw_key=raw_key, prefix=prefix, encoded_hash=encoded_hash)


def generate_source_api_key() -> GeneratedApiKey:
    """Generate a high-entropy source bearer key."""

    return _generate_api_key("src")


def generate_tenant_api_key() -> GeneratedApiKey:
    """Generate a high-entropy tenant bearer key."""

    return _generate_api_key("tnt")


def _extract_key_prefix(raw_key: str, kind: str) -> str | None:
    """Extract the public lookup prefix without exposing the secret portion."""

    parts = raw_key.split("_", maxsplit=2)
    if len(parts) != 3 or parts[0] != kind or len(parts[1]) != 12 or not parts[2]:
        return None
    return parts[1]


def extract_key_prefix(raw_key: str) -> str | None:
    """Extract a source key lookup prefix."""

    return _extract_key_prefix(raw_key, "src")


def extract_tenant_key_prefix(raw_key: str) -> str | None:
    """Extract a tenant key lookup prefix."""

    return _extract_key_prefix(raw_key, "tnt")


def verify_source_api_key(raw_key: str, encoded_hash: str) -> bool:
    """Verify a bearer key using constant-time digest comparison."""

    try:
        algorithm, n, r, p, encoded_salt, encoded_digest = encoded_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.scrypt(
            raw_key.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def verify_tenant_api_key(raw_key: str, encoded_hash: str) -> bool:
    """Verify a tenant bearer key using the shared scrypt representation."""

    return verify_source_api_key(raw_key, encoded_hash)
