"""Bound JSON request bodies before authentication and Pydantic parsing."""

import json
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from packages.observability.http import REQUEST_ID_PATTERN


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = 1024 * 1024) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        if headers.get(b"content-encoding", b"identity").lower() not in {b"", b"identity"}:
            await self._error(scope, send, 415, "unsupported_content_encoding")
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            body.extend(message.get("body", b""))
            if len(body) > self.max_body_bytes:
                await self._error(scope, send, 413, "request_too_large")
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    async def _error(self, scope: Scope, send: Send, status: int, code: str) -> None:
        supplied = (
            dict(scope.get("headers", []))
            .get(b"x-request-id", b"")
            .decode("ascii", errors="ignore")
        )
        request_id = scope.get("state", {}).get("request_id") or (
            supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else f"req_{uuid.uuid4()}"
        )
        content = json.dumps(
            {
                "error": {
                    "code": code,
                    "message": "Request body exceeds limit"
                    if status == 413
                    else "Only identity encoding is allowed",
                    "details": None,
                    "retryable": False,
                },
                "request_id": request_id,
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"x-request-id", request_id.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": content})
