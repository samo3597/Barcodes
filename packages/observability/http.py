"""HTTP middleware for request correlation and Prometheus metrics."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Accept a safe request ID or create one, then echo it to the client."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else f"req_{uuid.uuid4()}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def install_http_observability(app: FastAPI, service_name: str) -> None:
    """Attach request IDs, basic metrics, and the /metrics endpoint."""

    registry = CollectorRegistry()
    app.state.metrics_registry = registry
    requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ("service", "method", "route", "status"),
        registry=registry,
    )
    request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ("service", "method", "route"),
        registry=registry,
    )
    app.state.quota_outcomes = Counter(
        "quota_requests_total", "Quota enforcement outcomes", ("outcome",), registry=registry
    )

    app.add_middleware(RequestIdMiddleware)

    @app.middleware("http")
    async def record_metrics(
        request: Request,
        call_next: Callable[..., Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            route_path = getattr(request.scope.get("route"), "path", "unmatched")
            requests_total.labels(service_name, request.method, route_path, 500).inc()
            request_duration.labels(service_name, request.method, route_path).observe(
                time.perf_counter() - started
            )
            raise
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        requests_total.labels(service_name, request.method, route_path, response.status_code).inc()
        request_duration.labels(service_name, request.method, route_path).observe(
            time.perf_counter() - started
        )
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        refresh = getattr(app.state, "refresh_operational_metrics", None)
        if refresh is not None:
            await refresh()
        return PlainTextResponse(generate_latest(registry), media_type="text/plain; version=0.0.4")
