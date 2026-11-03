import { expect, it } from "vitest";
import { matchesExpectation, reduceResults } from "./attacks";

const ev = (outcome: string, ts = 1) => ({
  id: 1, ts, kind: "attack_result", src: "attacker",
  evidence: { attack: "read-postgres", outcome, expected: "succeeds" },
});

it("keeps only the latest result for an attack", () => {
  const r = reduceResults(reduceResults({}, ev("succeeds", 1)), ev("blocked", 2));
  expect(r["read-postgres"]).toMatchObject({ outcome: "blocked", ts: 2000 });
});
it("ignores unrelated events", () => {
  expect(reduceResults({}, { id: 1, ts: 0, kind: "http_request", src: "web", evidence: {} })).toEqual({});
});
it("compares the outcome with what the catalogue expects", () => {
  expect(matchesExpectation({ outcome: "succeeds", expected: "succeeds", ts: 0 })).toBe(true);
  expect(matchesExpectation({ outcome: "blocked", expected: "succeeds", ts: 0 })).toBe(false);
});
