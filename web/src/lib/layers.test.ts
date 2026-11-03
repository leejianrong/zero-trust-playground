import { afterEach, expect, test, vi } from "vitest";
import { LAYERS, MODES, setMode } from "./layers";

afterEach(() => vi.unstubAllGlobals());

const reply = (status: number, body: unknown) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));

test("a refused change returns the controller's reason unchanged", async () => {
  vi.stubGlobal("fetch", reply(409, { detail: "mTLS needs workload identity: turn identity on first" }));
  expect(await setMode("mtls", "enforce")).toEqual({ ok: false, reason: "mTLS needs workload identity: turn identity on first" });
});

test("an accepted change returns the new modes and sends the mode in the body", async () => {
  const fetchMock = reply(200, { identity: "audit", mtls: "off" });
  vi.stubGlobal("fetch", fetchMock);
  expect(await setMode("identity", "audit")).toEqual({ ok: true, modes: { identity: "audit", mtls: "off" } });
  expect(fetchMock).toHaveBeenCalledWith("/layers/identity", expect.objectContaining({ method: "PUT", body: '{"mode":"audit"}' }));
});

test("every layer explains every mode", () => {
  for (const layer of LAYERS) for (const m of MODES) expect(layer.modes[m.id].length).toBeGreaterThan(10);
});
