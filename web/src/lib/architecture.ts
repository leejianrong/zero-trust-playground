import type { Mode, Modes } from "./layers";

export type Node = { id: string; label: string; x: number; y: number; workload: boolean };
export type Edge = { from: string; to: string; guarded: boolean };

// One call path per line, as the clinic makes them. `guarded` is true where the mTLS layer applies.
export const NODES: Node[] = [
  { id: "user", label: "User", x: 20, y: 135, workload: false },
  { id: "web", label: "web", x: 160, y: 135, workload: true },
  { id: "billing", label: "billing", x: 340, y: 40, workload: true },
  { id: "records-api", label: "records-api", x: 340, y: 135, workload: true },
  { id: "agent", label: "agent", x: 340, y: 230, workload: true },
  { id: "records-mcp", label: "records-mcp", x: 520, y: 230, workload: true },
  { id: "postgres", label: "Postgres", x: 680, y: 135, workload: false },
];

export const EDGES: Edge[] = [
  { from: "user", to: "web", guarded: false },
  { from: "web", to: "billing", guarded: true },
  { from: "web", to: "records-api", guarded: true },
  { from: "web", to: "agent", guarded: true },
  { from: "billing", to: "records-api", guarded: true },
  { from: "agent", to: "records-mcp", guarded: true },
  { from: "records-mcp", to: "records-api", guarded: true },
  { from: "records-api", to: "postgres", guarded: false },
];

export type Status = "off" | "audit" | "enforce" | "partial" | "planned";

export type Layer = {
  id: string;
  name: string;
  component: string; // the Layered Zero Trust pattern component it maps to
  protects: string;
  slice: string;
  built: boolean;
};

export const PATTERN_LAYERS: Layer[] = [
  { id: "identity", name: "Workload identity", component: "SPIFFE and SPIRE", protects: "Every service can prove who it is, with a certificate that lives two minutes.", slice: "V1, V3", built: true },
  { id: "mtls", name: "Mutual TLS and authorisation", component: "SPIRE certificates with an allow-list", protects: "Services refuse callers they do not know, and callers that may not make this request.", slice: "V3", built: true },
  { id: "network", name: "Network policy", component: "Kubernetes network policies", protects: "A pod that is not on the list cannot even reach the database or the services.", slice: "V4", built: true },
  { id: "secrets", name: "Short-lived secrets", component: "HashiCorp Vault and External Secrets", protects: "The database password stops being shared and permanent.", slice: "V5", built: true },
  { id: "user", name: "User identity", component: "Keycloak", protects: "The services know which person a request is for.", slice: "V6", built: true },
  { id: "agent", name: "Agent scopes", component: "A playground addition for agents", protects: "An agent gets its own identity and only the tools it needs.", slice: "V6b", built: false },
];

export const status = (layer: Layer, modes: Modes): Status =>
  layer.built ? ((modes[layer.id] as Status | undefined) ?? "off") : "planned";

/** How an mTLS-guarded line is drawn. Shape differs as well as colour, so colour never carries it alone. */
export function lineFor(mtls: Mode | undefined): { dash: string; color: string; width: number; label: string } {
  switch (mtls) {
    case "enforce": return { dash: "", color: "var(--credential)", width: 3, label: "checked and refused when not allowed" };
    case "audit": return { dash: "8 5", color: "var(--expiry-fill)", width: 3, label: "checked and logged, not refused" };
    default: return { dash: "2 6", color: "var(--ink-soft)", width: 2, label: "not checked" };
  }
}
