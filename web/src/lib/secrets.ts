export type SecretEv = {
  id: number;
  ts: number; // seconds, from the Vault audit log
  kind: string;
  src: string | null;
  reason: string | null;
  evidence: Record<string, string | number>;
};

export type Credential = { lease: string; holder: string; role: string; issuedAt: number; ttlMs: number };
export type Refusal = { id: number; holder: string; at: number; reason: string };
export type Credentials = { live: Credential[]; refused: Refusal[] };

const KEEP = 12;

export function reduce(state: Credentials, ev: SecretEv): Credentials {
  if (ev.kind === "credential_issued" && ev.src) {
    const lease = String(ev.evidence.serial);
    if (state.live.some((c) => c.lease === lease)) return state;
    const cred: Credential = { lease, holder: ev.src, role: String(ev.evidence.role), issuedAt: ev.ts * 1000, ttlMs: Number(ev.evidence.ttl_s) * 1000 };
    return { ...state, live: [cred, ...state.live].sort((a, b) => b.issuedAt - a.issuedAt).slice(0, KEEP) };
  }
  if (ev.kind === "credential_denied" && ev.src) {
    return { ...state, refused: [{ id: ev.id, holder: ev.src, at: ev.ts * 1000, reason: ev.reason ?? "" }, ...state.refused].slice(0, KEEP) };
  }
  return state;
}

// Clamped to the lifetime: the page clock ticks once a second and can trail the audit timestamp.
export const secondsLeft = (c: Credential, now: number) =>
  Math.min(c.ttlMs / 1000, Math.max(0, Math.ceil((c.issuedAt + c.ttlMs - now) / 1000)));
export const isExpired = (c: Credential, now: number) => now >= c.issuedAt + c.ttlMs;
