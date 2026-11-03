export type Mode = "off" | "audit" | "enforce";
export type Modes = Record<string, Mode>;

export const MODES: { id: Mode; label: string }[] = [
  { id: "off", label: "Off" },
  { id: "audit", label: "Audit" },
  { id: "enforce", label: "Enforce" },
];

export type LayerInfo = { id: string; name: string; what: string; modes: Record<Mode, string>; noAudit?: string };

// What each mode does in this playground, as built. Keep in step with ADR-0010.
export const LAYERS: LayerInfo[] = [
  {
    id: "identity",
    name: "Workload identity",
    what: "Every service holds a short-lived SPIFFE identity from SPIRE.",
    modes: {
      off: "Services call each other over plain HTTP. Their identities exist but go unused.",
      audit: "Services call each other over mutual TLS and present their identity. Nobody checks it yet.",
      enforce: "Same as audit for now. Nothing refuses a caller until the mTLS layer is on.",
    },
  },
  {
    id: "mtls",
    name: "Mutual TLS and authorisation",
    what: "Services check who is calling, and whether that caller is allowed to make this request.",
    modes: {
      off: "Any call is accepted. No client certificate is even requested.",
      audit: "Each call is checked against the allow-list and a would-be refusal is logged. Nothing is refused. A forged certificate is still dropped during the TLS handshake, which cannot be logged.",
      enforce: "A caller with no valid identity, or one not on the allow-list, gets a 403 with a reason. Plain HTTP is refused except /healthz.",
    },
  },
  {
    id: "network",
    name: "Network policy",
    what: "Kubernetes decides which pods may open a connection to which. Anything not on the list is dropped.",
    modes: {
      off: "No policy. Any pod can open a connection to any service, including the database.",
      audit: "Not offered. A dropped connection leaves no log we can read.",
      enforce: "Default-deny on the clinic and agents namespaces, plus one allow for each real call. Only records-api reaches Postgres.",
    },
    noAudit: "Not available: a dropped connection leaves no log we can read, so there is nothing to show in audit.",
  },
];

export async function fetchModes(): Promise<Modes> {
  const r = await fetch("/layers");
  if (!r.ok) throw new Error(`observer answered ${r.status}`);
  return r.json();
}

/** Ask the controller to change one layer. The controller decides; its refusal reason is shown as is. */
export async function setMode(layer: string, mode: Mode): Promise<{ ok: true; modes: Modes } | { ok: false; reason: string }> {
  const r = await fetch(`/layers/${layer}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (r.ok) return { ok: true, modes: await r.json() };
  const body = await r.json().catch(() => ({}));
  return { ok: false, reason: typeof body.detail === "string" ? body.detail : `The controller answered ${r.status}.` };
}
