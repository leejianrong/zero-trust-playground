"""MCP front door to the clinic records. Baseline: no authentication, every tool open to any caller.

Tool calls are logged in the same shape as HTTP requests, so they show up on the Topology."""
import os

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from .common import client, emit, start_background, trace_var, user_token_var
from .guard import Guard

RECORDS = os.environ.get("RECORDS_URL", "http://records-api.clinic.svc:8080")
modes, _identity = start_background("records-mcp")
mcp = MCPServer("clinic-records", instructions="Look up and manage patient records for the Riverside Clinic.")


def call(ctx: Context, tool: str, method: str, path: str, body: dict | None = None):
    """Forward one tool call to records-api, passing the caller's trace id along."""
    headers = ctx.headers or {}
    trace = headers.get("x-trace-id") or "none"
    trace_var.set(trace)
    auth = headers.get("authorization", "")
    user_token_var.set(auth[7:].strip() if auth.lower().startswith("bearer ") else None)
    with client("records-mcp") as c:
        r = c.request(method, f"{RECORDS}{path}", json=body)
    emit(event="http", service="records-mcp", caller=headers.get("x-caller", "unknown"), method="TOOL",
         route=f"tool/{tool}", status=r.status_code, trace=trace)
    if r.is_error:  # say who refused and why, so the agent's caller sees more than a status code
        try:
            body = r.json()
        except ValueError:
            body = {}
        layer = f"{body['layer']} layer: " if body.get("layer") else ""
        raise ToolError(f"records-api answered {r.status_code}. {layer}{body.get('reason', r.text[:200])}")
    return r.json() if r.content else {"ok": True}


@mcp.tool()
def list_patients(ctx: Context) -> list[dict]:
    """List every patient record."""
    return call(ctx, "list_patients", "GET", "/patients")


@mcp.tool()
def get_patient(ctx: Context, patient_id: int) -> dict:
    """Fetch one patient record by id."""
    return call(ctx, "get_patient", "GET", f"/patients/{patient_id}")


@mcp.tool()
def update_patient(ctx: Context, patient_id: int, name: str, dob: str, diagnosis: str) -> dict:
    """Replace a patient's name, date of birth (YYYY-MM-DD) and diagnosis."""
    return call(ctx, "update_patient", "PUT", f"/patients/{patient_id}",
                {"name": name, "dob": dob, "diagnosis": diagnosis})


@mcp.tool()
def delete_patient(ctx: Context, patient_id: int) -> dict:
    """Delete a patient record permanently."""
    return call(ctx, "delete_patient", "DELETE", f"/patients/{patient_id}")


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):
    return JSONResponse({"ok": True})


# Host checking is off because the server is reached by in-cluster service names, and this
# playground only ever runs on localhost.
app = mcp.streamable_http_app(
    stateless_http=True, host="0.0.0.0",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
app.add_middleware(Guard, service="records-mcp", modes=modes)
