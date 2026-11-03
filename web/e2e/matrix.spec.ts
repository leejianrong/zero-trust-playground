import { expect, test, type APIRequestContext } from "@playwright/test";

// Every attack at every layer setting, checked against the catalogue. This is the V3 acceptance test:
// a denial the playground demonstrates is a denial this file asserts.
const OBSERVER = "http://localhost:8765";
const WEB = "http://localhost:8081";

// mTLS enforce needs identity on, so identity goes to audit for that row.
const SETTINGS = [
  { identity: "off", mtls: "off" },
  { identity: "audit", mtls: "audit" },
  { identity: "audit", mtls: "enforce" },
] as const;

async function setModes(request: APIRequestContext, identity: string, mtls: string) {
  // Order matters: the controller refuses mTLS on while identity is off, and identity off while mTLS is on.
  const steps = identity === "off" ? [["mtls", mtls], ["identity", identity]] : [["identity", identity], ["mtls", mtls]];
  for (const [layer, mode] of steps) {
    const r = await request.put(`${OBSERVER}/layers/${layer}`, { data: { mode } });
    expect(r.ok(), `${layer} to ${mode}`).toBe(true);
  }
  // The web service reports the modes it acts on. The others poll the same ConfigMap every 2 seconds.
  await expect.poll(async () => (await (await request.get(`${WEB}/healthz`)).json()).modes, { timeout: 10_000 })
    .toMatchObject({ identity, mtls });
  await new Promise((done) => setTimeout(done, 4_000));
}

test.afterAll(async ({ request }) => {
  await setModes(request, "off", "off");
});

for (const { identity, mtls } of SETTINGS) {
  test(`every attack matches the catalogue with identity ${identity} and mtls ${mtls}`, async ({ request }) => {
    test.setTimeout(240_000);
    await setModes(request, identity, mtls);
    const catalogue: { name: string }[] = await (await request.get(`${OBSERVER}/attacks`)).json();
    expect(catalogue.length).toBeGreaterThanOrEqual(6);
    for (const { name } of catalogue) {
      const ev = (await (await request.post(`${OBSERVER}/attacks/${name}/run`, { timeout: 60_000 })).json()).evidence;
      expect(ev.modes, name).toEqual({ identity, mtls });
      expect(ev.as_expected, `${name}: ${ev.outcome}, expected ${ev.expected}`).toBe(true);
      // A refusal that happens during a request names the layer. The forged certificate dies in the handshake first.
      if (ev.outcome === "blocked" && name !== "forged-identity") expect(ev.stopped_by, name).toBe("mtls");
      if (name === "forged-identity" && ev.outcome === "blocked") expect(ev.stopped_by).toBeNull();
    }
  });
}

test("the legitimate clinic and the agent still work with mtls enforced", async ({ request }) => {
  test.setTimeout(120_000);
  await setModes(request, "audit", "enforce");
  const patients = await request.get(`${WEB}/api/patients`);
  expect(patients.ok()).toBe(true);
  const summary = await request.post(`${WEB}/api/agent/summarise`, { timeout: 30_000 });
  expect(summary.ok()).toBe(true);
  expect((await summary.json()).summary).toMatch(/patients on file/);
});
