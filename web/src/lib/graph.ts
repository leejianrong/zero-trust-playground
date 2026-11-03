import type { Ev } from "./identity";

export type Edge = { src: string; dst: string; count: number; lastTs: number; verdict: "allow" | "deny" | "info" };
export type Graph = {
  nodes: Record<string, object>;
  registered: Record<string, string>; // service account -> SPIFFE ID, kept even before the node has traffic
  edges: Record<string, Edge>;
};

export const emptyGraph = (): Graph => ({ nodes: {}, registered: {}, edges: {} });

const serviceAccount = (spiffeId: string) => /\/sa\/([^/]+)$/.exec(spiffeId)?.[1];

export function reduceGraph(g: Graph, ev: Ev & { dst?: string | null; verdict?: string; layer?: string }): Graph {
  if (ev.kind === "entry_added" || ev.kind === "entry_removed") {
    const sa = ev.src && serviceAccount(ev.src);
    if (!sa) return g;
    const { [sa]: _gone, ...rest } = g.registered;
    return { ...g, registered: ev.kind === "entry_added" ? { ...rest, [sa]: ev.src! } : rest };
  }
  const traffic = ev.kind === "http_request" || ev.kind === "db_connect";
  // A permitted attack already shows up as real traffic. Only a blocked one needs its own edge.
  const blocked = ev.kind === "attack_result" && ev.verdict === "deny";
  if (!(traffic || blocked) || !ev.src || !ev.dst) return g;
  const key = `${ev.src}>${ev.dst}`;
  const prev = g.edges[key];
  const edge: Edge = {
    src: ev.src, dst: ev.dst, count: (prev?.count ?? 0) + 1, lastTs: ev.ts * 1000,
    verdict: (ev.verdict as Edge["verdict"]) ?? "info",
  };
  return {
    ...g,
    nodes: { ...g.nodes, [ev.src]: {}, [ev.dst]: {} },
    edges: { ...g.edges, [key]: edge },
  };
}

// Fixed slots so the picture is the same every time and learners can build a memory of it.
const SLOTS: Record<string, [number, number]> = {
  user: [90, 110], attacker: [90, 440], web: [290, 190], billing: [540, 90],
  "records-mcp": [540, 215], agent: [290, 340], "records-api": [540, 350], postgres: [810, 440],
};

export function layout(names: string[]): Record<string, { x: number; y: number }> {
  const out: Record<string, { x: number; y: number }> = {};
  let extra = 0;
  for (const name of [...names].sort()) {
    const slot = SLOTS[name];
    out[name] = slot ? { x: slot[0], y: slot[1] } : { x: 300 + 150 * extra++, y: 500 };
  }
  return out;
}

export const ageSeconds = (e: Edge, now: number) => Math.max(0, Math.round((now - e.lastTs) / 1000));

/** Shorten a centre-to-centre line so it starts and ends on the node boxes, where arrowheads stay visible. */
export function clip(a: { x: number; y: number }, b: { x: number; y: number }, hw: number, hh: number, gap = 4) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const t = Math.min(dx ? hw / Math.abs(dx) : Infinity, dy ? hh / Math.abs(dy) : Infinity);
  const len = Math.hypot(dx, dy) || 1;
  const pad = gap / len;
  return {
    start: { x: a.x + dx * (t + pad), y: a.y + dy * (t + pad) },
    end: { x: b.x - dx * (t + pad), y: b.y - dy * (t + pad) },
  };
}
