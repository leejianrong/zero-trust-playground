import { describe, expect, it } from "vitest";
import { isExpired, reduce, secondsLeft, type Credentials, type SecretEv } from "./secrets";

const issued = (id: number, lease: string, tsSeconds: number, holder = "records-api"): SecretEv => ({
  id, ts: tsSeconds, kind: "credential_issued", src: holder, reason: "issued",
  evidence: { serial: lease, ttl_s: 120, role: "records-api" },
});

describe("reduce", () => {
  it("lists a credential with its holder, issue time and lifetime", () => {
    const c = reduce({ live: [], refused: [] }, issued(1, "a", 1000));
    expect(c.live[0]).toMatchObject({ lease: "a", holder: "records-api", issuedAt: 1_000_000, ttlMs: 120_000 });
  });
  it("puts the newest first and ignores a repeated lease", () => {
    let c: Credentials = reduce({ live: [], refused: [] }, issued(1, "a", 1000));
    c = reduce(c, issued(2, "b", 1090));
    expect(c.live.map((x) => x.lease)).toEqual(["b", "a"]);
    expect(reduce(c, issued(3, "a", 1000))).toBe(c);
  });
  it("keeps only the newest 12", () => {
    let c: Credentials = { live: [], refused: [] };
    for (let i = 0; i < 20; i++) c = reduce(c, issued(i, `l${i}`, 1000 + i));
    expect(c.live).toHaveLength(12);
    expect(c.live[0].lease).toBe("l19");
  });
  it("records who was refused", () => {
    const c = reduce({ live: [], refused: [] }, { id: 1, ts: 5, kind: "credential_denied", src: "billing", reason: "billing was refused", evidence: {} });
    expect(c.refused[0]).toMatchObject({ holder: "billing", at: 5000 });
  });
  it("ignores unrelated events", () => {
    const c: Credentials = { live: [], refused: [] };
    expect(reduce(c, { id: 1, ts: 1, kind: "svid_issued", src: "x", reason: null, evidence: {} })).toBe(c);
  });
});

describe("time left", () => {
  const cred = reduce({ live: [], refused: [] }, issued(1, "a", 1000)).live[0];
  it("counts down to zero and never goes negative", () => {
    expect(secondsLeft(cred, 1_000_000)).toBe(120);
    expect(secondsLeft(cred, 1_060_000)).toBe(60);
    expect(secondsLeft(cred, 1_200_000)).toBe(0);
  });
  it("never shows more than the lifetime when the page clock is a little behind the audit log", () => {
    expect(secondsLeft(cred, 999_400)).toBe(120);
  });
  it("is expired exactly when the lifetime is up", () => {
    expect(isExpired(cred, 1_119_999)).toBe(false);
    expect(isExpired(cred, 1_120_000)).toBe(true);
  });
});
