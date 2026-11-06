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
# The signed-in user's access token for this request. Every outbound call carries it, so records-api can tell who it is for.
user_token_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_token", default=None)


def emit(**fields):
    print(json.dumps(fields), file=sys.stdout, flush=True)


_runtime: dict = {}


def layer_mode(layer: str) -> str:
    modes = _runtime.get("modes")
    return modes.get(layer) if modes else "off"


def start_background(service: str):
    """Start following the layer modes and fetching this workload's identity.

    Both are no-ops outside the cluster, so unit tests need no setup."""
    from clinic.identity import Identity
    from clinic.modes import Modes

    modes = Modes(service).start()
    identity = Identity(service)
    if os.environ.get("SPIFFE_ENDPOINT_SOCKET"):
        identity.start()
    _runtime.update(modes=modes, identity=identity)
    return modes, identity


def bearer_value(header: str) -> str | None:
    """The token in an `Authorization: Bearer <token>` header value, else None."""
    return header[7:].strip() if header.lower().startswith("bearer ") else None


def bearer(request: Request) -> str | None:
    return bearer_value(request.headers.get("authorization", ""))


def instrument(app: FastAPI, service: str, user_token=None) -> FastAPI:
    """`user_token(request)` says where this service gets the user's token. The default is the Authorization header."""
    from clinic.guard import Guard

    modes, _identity = start_background(service)
    # Added before the logging middleware below, so it sits inside it and refusals are logged too.
    app.add_middleware(Guard, service=service, modes=modes)

    @app.middleware("http")
    async def trace_and_log(request: Request, call_next):
        trace = request.headers.get("x-trace-id") or uuid.uuid4().hex[:12]
        trace_var.set(trace)
        user_token_var.set((user_token or bearer)(request))
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


def _mesh_material():
    """This workload's SVID, when the identity layer is on and SPIRE has issued one."""
    modes, identity = _runtime.get("modes"), _runtime.get("identity")
    if modes and identity and modes.get("identity") != "off":
        return identity.material()
    return None


def secure(url: str) -> str:
    """Services listen on 8080 (plain) and 8443 (mTLS). This points a cluster URL at the mTLS port."""
    if url.startswith("http://") and ".svc" in url and ":8080" in url:
        return url.replace("http://", "https://", 1).replace(":8080", ":8443", 1)
    return url


class _Mesh(httpx.Client):
    def build_request(self, method, url, **kwargs):
        url = str(url)
        return super().build_request(method, secure(url) if self._material else url, **kwargs)


def client(service: str) -> httpx.Client:
    """Outbound client that passes the current trace id and names the calling service.

    With the identity layer on it presents this workload's SVID over mTLS. The x-caller header
    stays for the dashboard, but the server trusts only the certificate."""
    from clinic.mtls import client_context

    headers = {"x-caller": service}
    if trace := trace_var.get():
        headers["x-trace-id"] = trace
    if token := user_token_var.get():
        headers["authorization"] = f"Bearer {token}"
    material = _mesh_material()
    c = _Mesh(headers=headers, timeout=5, verify=client_context(material) if material else True)
    c._material = material
    return c
