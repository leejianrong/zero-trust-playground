import type { Ev } from "./identity";

export type Attack = { name: string; title: string; description: string; target: string; expected: Record<string, string> };
export type Result = { outcome: "succeeds" | "blocked"; expected: string; ts: number };
export type Results = Record<string, Result>;

/** Keep the latest result per attack. */
export function reduceResults(r: Results, ev: Ev & { evidence: Record<string, unknown> }): Results {
  if (ev.kind !== "attack_result") return r;
  const e = ev.evidence as { attack: string; outcome: Result["outcome"]; expected: string };
  return { ...r, [e.attack]: { outcome: e.outcome, expected: e.expected, ts: ev.ts * 1000 } };
}

export const matchesExpectation = (r: Result) => r.outcome === r.expected;
