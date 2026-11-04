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
