"""Create a Server 2 tenant and print its API key exactly once."""

import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.api_keys import generate_tenant_api_key
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.models import Tenant, TenantApiKey

DEFAULT_SCOPES = [
    "products:read",
    "categories:read",
    "usage:read",
    "feedback:write",
    "changes:read",
]


async def create_tenant(code: str, name: str, scopes: list[str], database_url: str) -> str:
    engine = build_engine(database_url)
    generated = generate_tenant_api_key()
    try:
        async with build_session_factory(engine)() as session:
            await _persist_tenant(
                session,
                code,
                name,
                scopes,
                generated.prefix,
                generated.encoded_hash,
            )
    finally:
        await engine.dispose()
    return generated.raw_key


async def _persist_tenant(
    session: AsyncSession,
    code: str,
    name: str,
    scopes: list[str],
    key_prefix: str,
    key_hash: str,
) -> None:
    tenant = Tenant(code=code, name=name, status="active", plan_config={})
    session.add(tenant)
    await session.flush()
    session.add(
        TenantApiKey(
            tenant_id=tenant.id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            status="active",
        )
    )
    await session.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", help="Stable unique tenant code")
    parser.add_argument("--name", help="Display name; defaults to the code")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        choices=[
            "products:read",
            "categories:read",
            "usage:read",
            "feedback:write",
            "changes:read",
        ],
        help="Repeat for each scope; defaults to all tenant-facing API scopes",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://barcodes:barcodes@localhost:5434/barcodes_server2",
    )
    raw_key = asyncio.run(
        create_tenant(
            args.code,
            args.name or args.code,
            args.scopes or DEFAULT_SCOPES,
            database_url,
        )
    )
    print("Tenant created. Save this API key now; it will not be shown again:")
    print(raw_key)


if __name__ == "__main__":
    main()
