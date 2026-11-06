export type UserEv = {
  id: number;
  ts: number; // seconds
  kind: string;
  verdict: string;
  src: string | null;
  dst: string | null;
  reason: string | null;
  evidence: Record<string, unknown>;
};

export type Person = { user: string; roles: string[]; signedIn: boolean; logins: number; refused: number; client: string; lastSeen: number };
export type Request = { id: number; at: number; user: string; client: string | null; audience: string[]; method: string; route: string; verdict: string; reason: string };
export type Failure = { id: number; at: number; reason: string };
export type Users = { people: Record<string, Person>; requests: Request[]; failures: Failure[] };

const KEEP = 12;
const ANON = "anonymous";

export function reduce(state: Users, ev: UserEv): Users {
  const who = ev.src ?? ANON;
  const at = ev.ts * 1000;
  const person = state.people[who];
  if (ev.kind === "user_login") {
    const p: Person = { user: who, roles: person?.roles ?? [], signedIn: true, logins: (person?.logins ?? 0) + 1, refused: person?.refused ?? 0, client: ev.dst ?? "", lastSeen: at };
    return { ...state, people: { ...state.people, [who]: p } };
  }
  if (ev.kind === "user_logout" && person) {
    return { ...state, people: { ...state.people, [who]: { ...person, signedIn: false, lastSeen: at } } };
  }
  if (ev.kind === "user_login_failed" || ev.kind === "user_token_refused") {
    return { ...state, failures: [{ id: ev.id, at, reason: ev.reason ?? "" }, ...state.failures].slice(0, KEEP) };
  }
  if (ev.kind === "user_authorisation") {
    const e = ev.evidence;
    const req: Request = { id: ev.id, at, user: who, client: (e.client as string | null) ?? null, audience: (e.audience as string[]) ?? [],
      method: String(e.method ?? ""), route: String(e.route ?? ""), verdict: ev.verdict, reason: ev.reason ?? "" };
    const people = who === ANON ? state.people : {
      ...state.people,
      [who]: { user: who, roles: (e.roles as string[])?.length ? (e.roles as string[]) : (person?.roles ?? []), signedIn: person?.signedIn ?? false,
        logins: person?.logins ?? 0, refused: (person?.refused ?? 0) + (ev.verdict === "deny" ? 1 : 0), client: person?.client ?? (req.client ?? ""), lastSeen: at },
    };
    return { ...state, people, requests: [req, ...state.requests].slice(0, KEEP) };
  }
  return state;
}
