import { expect, test } from "vitest";
import { EDGES, NODES, PATTERN_LAYERS, lineFor, status } from "./architecture";

test("every edge joins two known nodes", () => {
  const ids = new Set(NODES.map((n) => n.id));
  for (const e of EDGES) expect([ids.has(e.from), ids.has(e.to)]).toEqual([true, true]);
});

test("the guarded line looks different in each mode, by shape as well as colour", () => {
  const looks = (["off", "audit", "enforce"] as const).map((m) => lineFor(m));
  expect(new Set(looks.map((l) => l.dash)).size).toBe(3);
  expect(new Set(looks.map((l) => l.label)).size).toBe(3);
});

test("a built layer follows the live mode and a planned layer stays planned", () => {
  const [identity, , network, secrets] = PATTERN_LAYERS;
  expect(status(identity, { identity: "audit", mtls: "off" })).toBe("audit");
  expect(status(identity, {})).toBe("off");
  expect(status(network, { network: "enforce" })).toBe("enforce");
  expect(status(secrets, { secrets: "enforce" })).toBe("planned");
});

test("every layer names the pattern component it maps to", () => {
  for (const l of PATTERN_LAYERS) expect(l.component.length).toBeGreaterThan(3);
});
