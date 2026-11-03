import { describe, expect, it } from "vitest";
import { isExpired, lifeLeft, parseSpiffeId, reduce, secondsLeft, type Cards, type Ev } from "./identity";

const ID = "spiffe://playground.local/ns/clinic/sa/echo-a";
const svidEv = (id: number, serial: string, nb = "2026-11-03T04:00:00Z", na = "2026-11-03T04:02:00Z"): Ev => ({
  id, ts: 0, kind: "svid_issued", src: ID,
  evidence: { serial, workload: "echo-a", not_before: nb, not_after: na },
});

describe("reduce", () => {
  it("adds a card, then prepends history on rotation", () => {
    let c: Cards = reduce({}, svidEv(1, "a"));
    c = reduce(c, svidEv(2, "b"));
    expect(c[ID].history.map((s) => s.serial)).toEqual(["b", "a"]);
  });
  it("ignores a repeated serial", () => {
    const c = reduce({}, svidEv(1, "a"));
    expect(reduce(c, svidEv(2, "a"))).toBe(c);
  });
  it("flags and clears registration removal", () => {
    let c = reduce({}, svidEv(1, "a"));
    c = reduce(c, { id: 2, ts: 0, kind: "entry_removed", src: ID, evidence: {} });
    expect(c[ID].registrationRemoved).toBe(true);
    c = reduce(c, svidEv(3, "b"));
    expect(c[ID].registrationRemoved).toBe(false);
  });
  it("ignores entry events for workloads with no card", () => {
    expect(reduce({}, { id: 1, ts: 0, kind: "entry_added", src: ID, evidence: {} })).toEqual({});
  });
  it("keeps only the latest 8 SVIDs", () => {
    let c: Cards = {};
    for (let i = 0; i < 12; i++) c = reduce(c, svidEv(i, `s${i}`));
    expect(c[ID].history).toHaveLength(8);
  });
});

describe("countdown", () => {
  const svid = { serial: "a", notBefore: 0, notAfter: 120_000 };
  it("is full at issue, half at the midpoint, and empty after expiry", () => {
    expect(lifeLeft(svid, 0)).toBe(1);
    expect(lifeLeft(svid, 60_000)).toBe(0.5);
    expect(lifeLeft(svid, 500_000)).toBe(0);
  });
  it("never goes negative and flips to expired at zero", () => {
    expect(secondsLeft(svid, 500_000)).toBe(0);
    expect(isExpired(svid, 119_999)).toBe(false);
    expect(isExpired(svid, 120_000)).toBe(true);
  });
});

describe("parseSpiffeId", () => {
  it("splits trust domain, namespace and service account", () => {
    expect(parseSpiffeId(ID)).toEqual({ trustDomain: "playground.local", namespace: "clinic", serviceAccount: "echo-a" });
  });
  it("returns null for ids outside the playground shape", () => {
    expect(parseSpiffeId("spiffe://x/y")).toBeNull();
  });
});
