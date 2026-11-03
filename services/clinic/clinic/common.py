"""Shared plumbing for the toy services: trace ids and one structured event per request.

The X-Trace-Id and X-Caller headers are observability aids, not security controls.
Any client can set them to anything."""
import contextvars
import json
import os
import sys
import uuid

import httpx
from fastapi import FastAPI, Request

trace_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace", default=None)


def emit(**fields):
    print(json.dumps(fields), file=sys.stdout, flush=True)


def start_background(service: str):
    """Start following the layer modes and fetching this workload's identity.

    Both are no-ops outside the cluster, so unit tests need no setup."""
    from clinic.identity import Identity
    from clinic.modes import Modes

    modes = Modes(service).start()
    identity = Identity(service)
    if os.environ.get("SPIFFE_ENDPOINT_SOCKET"):
        identity.start()
    return modes, identity


def instrument(app: FastAPI, service: str) -> FastAPI:
    modes, _identity = start_background(service)

    @app.middleware("http")
    async def trace_and_log(request: Request, call_next):
        trace = request.headers.get("x-trace-id") or uuid.uuid4().hex[:12]
        trace_var.set(trace)
        response = await call_next(request)
        response.headers["x-trace-id"] = trace
        if request.url.path != "/healthz":
            emit(event="http", service=service, caller=request.headers.get("x-caller", "unknown"),
                 method=request.method, route=request.url.path, status=response.status_code, trace=trace)
        return response

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "modes": modes.all()}

    return app


def client(service: str) -> httpx.Client:
    """Outbound client that passes the current trace id and names the calling service."""
    headers = {"x-caller": service}
    if trace := trace_var.get():
        headers["x-trace-id"] = trace
    return httpx.Client(headers=headers, timeout=5)
