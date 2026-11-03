import { describe, expect, it } from "vitest";
import { clip, emptyGraph, layout, reduceGraph } from "./graph";

const http = (src: string, dst: string, ts = 10) => ({
  id: 1, ts, kind: "http_request", src, dst, verdict: "allow", layer: "app", evidence: {},
});

describe("reduceGraph", () => {
  it("creates both nodes and counts repeated calls on one edge", () => {
    let g = reduceGraph(emptyGraph(), http("web", "records-api"));
    g = reduceGraph(g, http("web", "records-api", 20));
    expect(Object.keys(g.nodes).sort()).toEqual(["records-api", "web"]);
    expect(g.edges["web>records-api"]).toMatchObject({ count: 2, lastTs: 20_000 });
  });
  it("treats a Postgres login as an edge", () => {
    const g = reduceGraph(emptyGraph(), { ...http("attacker", "postgres"), kind: "db_connect" });
    expect(g.edges["attacker>postgres"].verdict).toBe("allow");
  });
  it("draws a blocked attack but not a permitted one", () => {
    const attack = (verdict: string) => ({ ...http("attacker", "billing"), kind: "attack_result", verdict });
    expect(reduceGraph(emptyGraph(), attack("allow")).edges).toEqual({});
    expect(reduceGraph(emptyGraph(), attack("deny")).edges["attacker>billing"].verdict).toBe("deny");
  });
  it("remembers a registration even when it arrives before any traffic", () => {
    const entry = (kind: string) => ({ id: 2, ts: 0, kind, src: "spiffe://playground.local/ns/clinic/sa/web", evidence: {} });
    let g = reduceGraph(emptyGraph(), entry("entry_added"));
    expect(g.registered.web).toContain("sa/web");
    g = reduceGraph(g, http("web", "billing"));
    expect(g.registered.web).toContain("sa/web");
    expect(reduceGraph(g, entry("entry_removed")).registered.web).toBeUndefined();
  });
  it("ignores events it does not draw", () => {
    const g = emptyGraph();
    expect(reduceGraph(g, { id: 1, ts: 0, kind: "svid_issued", src: "x", evidence: {} })).toBe(g);
  });
});

describe("layout", () => {
  it("is deterministic and independent of input order", () => {
    expect(layout(["postgres", "web", "user"])).toEqual(layout(["user", "web", "postgres"]));
  });
  it("gives unknown workloads their own slots without overlapping known ones", () => {
    const l = layout(["web", "mystery-a", "mystery-b"]);
    expect(l["mystery-a"]).not.toEqual(l["mystery-b"]);
    expect(l.web).toEqual({ x: 290, y: 190 });
  });
});

describe("clip", () => {
  it("moves a line's ends from the node centres to the box edges", () => {
    const { start, end } = clip({ x: 0, y: 0 }, { x: 400, y: 0 }, 75, 27, 0);
    expect(start).toEqual({ x: 75, y: 0 });
    expect(end).toEqual({ x: 325, y: 0 });
  });
  it("uses the top and bottom edges for a mostly vertical line", () => {
    const { start } = clip({ x: 0, y: 0 }, { x: 0, y: 300 }, 75, 27, 0);
    expect(start).toEqual({ x: 0, y: 27 });
  });
});
