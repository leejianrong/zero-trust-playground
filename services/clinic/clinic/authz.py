"""Who may call what (ADR-0010). The allow-list is the whole policy: a caller's SPIFFE ID, the
methods it may use and the routes it may reach. A service not listed here accepts everyone."""
import re

TRUST_DOMAIN = "playground.local"


def spiffe(namespace: str, account: str) -> str:
    return f"spiffe://{TRUST_DOMAIN}/ns/{namespace}/sa/{account}"


WEB, BILLING = spiffe("clinic", "web"), spiffe("clinic", "billing")
MCP, AGENT = spiffe("clinic", "records-mcp"), spiffe("agents", "agent")
ANY = "*"
PATIENTS = r"/patients(/\d+)?"

ALLOW: dict[str, list[tuple[str, str, str]]] = {
    "records-api": [(WEB, ANY, PATIENTS), (BILLING, "GET", r"/patients/\d+"), (MCP, ANY, PATIENTS)],
    "billing": [(WEB, "GET", r"/invoices/\d+")],
    "records-mcp": [(AGENT, ANY, r"/mcp/?")],
    "agent": [(WEB, "POST", r"/tasks/summarise")],
}


def refusal(service: str, caller: str | None, method: str, path: str, tls: bool) -> str | None:
    """Why this request should be refused, or None if it is allowed."""
    if service not in ALLOW:
        return None
    if not tls:
        return "plain connection: no identity can be proven"
    if caller is None:
        return "no client certificate presented"
    for who, methods, route in ALLOW[service]:
        if who == caller and methods in (ANY, method) and re.fullmatch(route, path):
            return None
    return f"{caller} is not allowed to {method} {path} on {service}"


def decide(service: str, mode: str, caller: str | None, method: str, path: str, tls: bool):
    """(verdict, reason). Verdict is allow, would_deny (audit) or deny (enforce)."""
    why = refusal(service, caller, method, path, tls)
    if why is None:
        return "allow", None
    return ("deny" if mode == "enforce" else "would_deny"), why
