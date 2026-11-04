import { expect, test, type APIRequestContext } from "@playwright/test";

// Every attack at every layer setting, checked against the catalogue, including the network layer on its own and
// together with mtls. This is the V3 and V4 acceptance test: a denial the playground demonstrates is a denial this
// file asserts.
const OBSERVER = "http://localhost:8765";
const WEB = "http://localhost:8081";

// mTLS enforce needs identity on, so identity goes to audit for that row.
const SETTINGS = [
  { identity: "off", mtls: "off", network: "off", secrets: "off" },
  { identity: "audit", mtls: "audit", network: "off", secrets: "off" },
  { identity: "audit", mtls: "enforce", network: "off", secrets: "off" },
  { identity: "off", mtls: "off", network: "enforce", secrets: "off" },
  { identity: "audit", mtls: "enforce", network: "enforce", secrets: "off" },
  { identity: "off", mtls: "off", network: "off", secrets: "enforce" },
  { identity: "audit", mtls: "enforce", network: "enforce", secrets: "enforce" },
] as const;

// The attacks that log in to Postgres with the leaked static password: the secrets layer is what stops them.
const LEAKED_PASSWORD = ["read-postgres", "postgres-from-billing"];

async function setModes(request: APIRequestContext, identity: string, mtls: string, network = "off", secrets = "off") {
  // Order matters: the controller refuses mTLS on while identity is off, and identity off while mTLS is on.
  const steps = identity === "off" ? [["mtls", mtls], ["identity", identity]] : [["identity", identity], ["mtls", mtls]];
  for (const [layer, mode] of steps) {
    const r = await request.put(`${OBSERVER}/layers/${layer}`, { data: { mode } });
    expect(r.ok(), `${layer} to ${mode}`).toBe(true);
  }
  const r = await request.put(`${OBSERVER}/layers/network`, { data: { mode: network } });
  expect(r.ok(), `network to ${network}`).toBe(true);
  const s = await request.put(`${OBSERVER}/layers/secrets`, { data: { mode: secrets }, timeout: 60_000 });
  expect(s.ok(), `secrets to ${secrets}: ${await s.text()}`).toBe(true);
  // The web service reports the modes it acts on. The others poll the same ConfigMap every 2 seconds.
  await expect.poll(async () => (await (await request.get(`${WEB}/healthz`)).json()).modes, { timeout: 10_000 })
    .toMatchObject({ identity, mtls });
  await new Promise((done) => setTimeout(done, 4_000));
}

test.afterAll(async ({ request }) => {
  await setModes(request, "off", "off", "off", "off");
});

for (const { identity, mtls, network, secrets } of SETTINGS) {
  test(`every attack matches the catalogue with identity ${identity}, mtls ${mtls}, network ${network} and secrets ${secrets}`, async ({ request }) => {
    test.setTimeout(300_000);
    await setModes(request, identity, mtls, network, secrets);
    const catalogue: { name: string }[] = await (await request.get(`${OBSERVER}/attacks`)).json();
    expect(catalogue.length).toBeGreaterThanOrEqual(7);
    for (const { name } of catalogue) {
      const ev = (await (await request.post(`${OBSERVER}/attacks/${name}/run`, { timeout: 60_000 })).json()).evidence;
      expect(ev.modes, name).toMatchObject({ identity, mtls, network, secrets });
      expect(ev.as_expected, `${name}: ${ev.outcome}, expected ${ev.expected}`).toBe(true);
      if (ev.outcome !== "blocked") continue;
      // A dropped connection never reaches a service, so the network is named (as an inference) whenever it is
      // enforced. Otherwise a refusal during a request names mtls, and the forged certificate dies in the handshake
      // before any request, so no layer is named.
      // A rejected password names secrets (inferred) when the network did not get there first.
      if (network === "enforce") expect(ev.stopped_by, name).toBe("network (inferred)");
      else if (secrets === "enforce" && LEAKED_PASSWORD.includes(name)) expect(ev.stopped_by, name).toBe("secrets (inferred)");
      else if (name === "forged-identity") expect(ev.stopped_by, name).toBeNull();
      else expect(ev.stopped_by, name).toBe("mtls");
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

test("the legitimate clinic and the agent still work with the network enforced, alone and with mtls", async ({ request }) => {
  test.setTimeout(180_000);
  for (const [identity, mtls] of [["off", "off"], ["audit", "enforce"]]) {
    await setModes(request, identity, mtls, "enforce");
    const patients = await request.get(`${WEB}/api/patients`);
    expect(patients.ok(), `patients with mtls ${mtls}`).toBe(true);
    const summary = await request.post(`${WEB}/api/agent/summarise`, { timeout: 30_000 });
    expect(summary.ok(), `summary with mtls ${mtls}`).toBe(true);
    expect((await summary.json()).summary).toMatch(/patients on file/);
  }
});

test("the legitimate clinic and the agent still work with secrets enforced", async ({ request }) => {
  test.setTimeout(180_000);
  await setModes(request, "off", "off", "off", "enforce");
  expect((await request.get(`${WEB}/api/patients`)).ok()).toBe(true);
  const summary = await request.post(`${WEB}/api/agent/summarise`, { timeout: 30_000 });
  expect(summary.ok()).toBe(true);
  expect((await summary.json()).summary).toMatch(/patients on file/);
});
