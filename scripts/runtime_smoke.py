"""Exercise the built non-root image's liveness, OpenAPI and optional DB readiness."""

import argparse
import asyncio
import os

from httpx import ASGITransport, AsyncClient

from apps.public_api.main import create_app


async def run(readiness: bool) -> None:
    if os.getuid() == 0:
        raise RuntimeError("runtime image must not execute as root")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://smoke") as client:
            assert (await client.get("/health/live")).status_code == 200
            schema = (await client.get("/openapi.json")).json()
            assert "/v1/feedback" in schema["paths"]
            assert "/v1/changes" in schema["paths"]
            if readiness:
                assert (await client.get("/health/ready")).status_code == 200
    print("PASS non-root runtime HTTP smoke")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready", action="store_true")
    asyncio.run(run(parser.parse_args().ready))
