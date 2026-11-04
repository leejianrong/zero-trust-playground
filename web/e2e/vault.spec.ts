import { expect, test } from "@playwright/test";
import { execFileSync, spawnSync } from "node:child_process";
import { resolve } from "node:path";

// V5 install: a workload logs in to Vault with its JWT-SVID and only to its own role (ADR-0012).
// Tokens stay in memory here and are never logged.
const KUBECTL = ["--context", "k3d-ztp"];
const ROOT = resolve(process.cwd(), "..");
const SERVICES = ["web", "records-api", "billing", "records-mcp"];

const JWT_SCRIPT = `
from spiffe import WorkloadApiClient
with WorkloadApiClient(socket_path="unix:///spiffe-workload-api/spire-agent.sock") as c:
    print(c.fetch_jwt_svid(audience={"vault"}).token)
`;

function jwtFor(service: string): string {
  return execFileSync("kubectl", [...KUBECTL, "-n", "clinic", "exec", "-i", `deploy/${service}`, "--", "python", "-"],
    { input: JWT_SCRIPT, encoding: "utf8" }).trim();
}

function login(role: string, jwt: string): { ok: boolean; error: string } {
  const r = spawnSync("kubectl", [...KUBECTL, "-n", "vault", "exec", "-i", "deploy/vault", "--", "env", "VAULT_ADDR=http://127.0.0.1:8200",
    "vault", "write", "-format=json", "auth/jwt/login", `role=${role}`, "jwt=-"], { input: jwt, encoding: "utf8" });
  const ttl = r.status === 0 ? JSON.parse(r.stdout).auth?.lease_duration : 0;
  return { ok: ttl > 0, error: r.stderr };
}

test.describe.configure({ mode: "serial" });

for (const service of SERVICES) {
  test(`${service} logs in to its own role`, () => {
    expect(login(service, jwtFor(service))).toMatchObject({ ok: true });
  });
}

test("billing's identity is refused on the records-api role", () => {
  const r = login("records-api", jwtFor("billing"));
  expect(r.ok).toBe(false);
  expect(r.error).toContain("invalid subject");
});

test("the configure script can run again and changes nothing", () => {
  const run = () => execFileSync("sh", [`${ROOT}/scripts/vault-configure.sh`], { encoding: "utf8" });
  expect(() => { run(); run(); }).not.toThrow();
  expect(login("records-api", jwtFor("records-api")).ok).toBe(true);
});

// AAL-32: dynamic Postgres users, and the static password that can be revoked and restored.
function inRecordsApi(script: string, input: object): { ok: boolean; out: string } {
  const r = spawnSync("kubectl", [...KUBECTL, "-n", "clinic", "exec", "-i", "deploy/records-api", "--", "python", "-c", script],
    { input: JSON.stringify(input), encoding: "utf8" });
  return { ok: r.status === 0, out: (r.stdout + r.stderr).trim().split("\n").pop() ?? "" };
}

const COUNT = `
import json, sys, psycopg
c = json.load(sys.stdin)
with psycopg.connect(host="postgres.clinic.svc", dbname="clinic", user=c["user"], password=c["password"], connect_timeout=5) as conn:
    print(conn.execute("select count(*) from patients").fetchone()[0])
`;

function issue(service: string): { user: string; password: string; ttl: number } | { denied: string } {
  const r = spawnSync("kubectl", [...KUBECTL, "-n", "vault", "exec", "-i", "deploy/vault", "--", "sh", "-c",
    `export VAULT_ADDR=http://127.0.0.1:8200; T=$(vault write -field=token auth/jwt/login role=${service} jwt=- 2>/dev/null) && VAULT_TOKEN=$T vault read -format=json database/creds/records-api`],
    { input: jwtFor(service), encoding: "utf8", env: { ...process.env } });
  if (r.status !== 0) return { denied: r.stderr };
  const d = JSON.parse(r.stdout);
  return { user: d.data.username, password: d.data.password, ttl: d.lease_duration };
}

const staticPassword = () =>
  Buffer.from(execFileSync("kubectl", [...KUBECTL, "-n", "clinic", "get", "secret", "db-static", "-o", "jsonpath={.data.password}"],
    { encoding: "utf8" }), "base64").toString();

test("records-api can be issued a Postgres user that reads patients, billing cannot", () => {
  const cred = issue("records-api");
  expect(cred).toHaveProperty("ttl", 120);
  const c = cred as { user: string; password: string };
  expect(inRecordsApi(COUNT, c)).toMatchObject({ ok: true, out: "5" });
  expect(issue("billing")).toHaveProperty("denied");
});

test("the static password can be revoked and restored", () => {
  const pw = staticPassword();
  const asStatic = () => inRecordsApi(COUNT, { user: "clinic", password: pw }).ok;
  try {
    execFileSync("sh", [`${ROOT}/scripts/db-static.sh`, "revoke"]);
    expect(asStatic()).toBe(false);
  } finally {
    execFileSync("sh", [`${ROOT}/scripts/db-static.sh`, "restore"]);
  }
  expect(asStatic()).toBe(true);
});

test("an issued user stops working after its TTL", async () => {
  test.setTimeout(240_000);
  const c = issue("records-api") as { user: string; password: string; ttl: number };
  expect(inRecordsApi(COUNT, c).ok).toBe(true);
  await new Promise((done) => setTimeout(done, (c.ttl + 15) * 1000));
  expect(inRecordsApi(COUNT, c).ok).toBe(false);
});
