"""The check at each service's door: look up who is calling, decide, log, and refuse if enforcing."""
import json
import uuid

from clinic.authz import decide
from clinic.common import emit, trace_var
from clinic.modes import Modes
from clinic.mtls import PEERS, Peers


class Guard:
    """ASGI middleware. In `off` it does nothing. Otherwise every request gets one `authz` event."""

    def __init__(self, app, service: str, modes: Modes, peers: Peers = PEERS):
        self.app, self.service, self.modes, self.peers = app, service, modes, peers

    async def __call__(self, scope, receive, send):
        mode = self.modes.get("mtls")
        if scope["type"] != "http" or mode == "off" or scope["path"] == "/healthz":
            return await self.app(scope, receive, send)
        tls = scope.get("scheme") == "https"
        caller = self.peers.caller(scope) if tls else None
        method, path = scope["method"], scope["path"]
        verdict, why = decide(self.service, mode, caller, method, path, tls)
        headers = dict(scope["headers"])
        trace = trace_var.get() or headers.get(b"x-trace-id", b"").decode() or uuid.uuid4().hex[:12]
        emit(event="authz", service=self.service, mode=mode, caller=caller, method=method, route=path,
             listener="mtls" if tls else "plain", verdict=verdict, reason=why, trace=trace)
        if verdict != "deny":
            return await self.app(scope, receive, send)
        body = json.dumps({"error": "refused", "reason": why, "trace": trace}).encode()
        await send({"type": "http.response.start", "status": 403, "headers": [
            (b"content-type", b"application/json"), (b"x-trace-id", trace.encode())]})
        await send({"type": "http.response.body", "body": body})
