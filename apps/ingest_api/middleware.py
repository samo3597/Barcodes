"""Request-body limits and gzip decoding for the batch endpoint."""

import json
import uuid
import zlib

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from packages.observability.http import REQUEST_ID_PATTERN

INGEST_MAX_BODY_BYTES = 10 * 1024 * 1024


class IngestBodyMiddleware:
    """Decode gzip and enforce the 10 MiB uncompressed batch limit."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = INGEST_MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/ingest/v1/batches":
            await self.app(scope, receive, send)
            return

        compressed = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                continue
            compressed.extend(message.get("body", b""))
            if len(compressed) > self.max_body_bytes:
                await self._send_error(scope, send, 413, "request_too_large", "Body exceeds 10 MiB")
                return
            more_body = bool(message.get("more_body", False))

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        encoding = headers.get(b"content-encoding", b"identity").decode("ascii", errors="ignore")
        try:
            body = self._decode(bytes(compressed), encoding)
        except ValueError as error:
            code = (
                "unsupported_content_encoding"
                if encoding not in {"identity", "gzip", ""}
                else "invalid_gzip"
            )
            status_code = 415 if code == "unsupported_content_encoding" else 400
            await self._send_error(scope, send, status_code, code, str(error))
            return

        if len(body) > self.max_body_bytes:
            await self._send_error(scope, send, 413, "request_too_large", "Body exceeds 10 MiB")
            return

        updated_scope = dict(scope)
        updated_headers = [
            (key, value)
            for key, value in scope.get("headers", [])
            if key.lower() not in {b"content-encoding", b"content-length"}
        ]
        updated_headers.append((b"content-length", str(len(body)).encode("ascii")))
        updated_scope["headers"] = updated_headers

        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(updated_scope, replay_receive, send)

    def _decode(self, body: bytes, encoding: str) -> bytes:
        if encoding in {"", "identity"}:
            return body
        if encoding != "gzip":
            raise ValueError(f"Unsupported Content-Encoding: {encoding}")

        try:
            decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
            decoded = decoder.decompress(body, self.max_body_bytes + 1)
            if len(decoded) > self.max_body_bytes or decoder.unconsumed_tail:
                return decoded
            decoded += decoder.flush(self.max_body_bytes + 1 - len(decoded))
        except zlib.error as error:
            raise ValueError("Request body is not valid gzip data") from error
        if not decoder.eof or decoder.unused_data:
            raise ValueError("Request body is not one valid gzip stream")
        return decoded

    async def _send_error(
        self,
        scope: Scope,
        send: Send,
        status_code: int,
        code: str,
        message: str,
    ) -> None:
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else f"req_{uuid.uuid4()}"
        payload = json.dumps(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": None,
                    "retryable": False,
                },
                "request_id": request_id,
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                    (b"x-request-id", request_id.encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})
