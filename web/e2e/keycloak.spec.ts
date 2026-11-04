import { expect, test } from "@playwright/test";
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { resolve } from "node:path";

// V6 install: the clinic realm has two users with one role each, and the issuer is the same
// from a pod and from the browser's side of a port-forward (ADR-0013).
const KUBECTL = ["--context", "k3d-ztp"];
const ROOT = resolve(process.cwd(), "..");
const ISSUER = "http://localhost:8180/realms/clinic";

const kcadm = (...args: string[]) =>
  execFileSync("kubectl", [...KUBECTL, "-n", "keycloak", "exec", "deploy/keycloak", "--", "/opt/keycloak/bin/kcadm.sh", ...args],
    { encoding: "utf8" });

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  kcadm("config", "credentials", "--server", "http://localhost:8080", "--realm", "master", "--user", "admin", "--password", "playground-dev-admin");
});

for (const [user, role, other] of [["aisha", "clinician", "receptionist"], ["bob", "receptionist", "clinician"]]) {
  test(`${user} has the ${role} role and not ${other}`, () => {
    const roles = kcadm("get-roles", "-r", "clinic", "--uusername", user, "--effective", "--fields", "name", "--format", "csv", "--noquotes");
    expect(roles).toContain(role);
    expect(roles).not.toContain(other);
  });
}

test("web is a public client that needs PKCE and records-api is bearer only", () => {
  const web = JSON.parse(kcadm("get", "clients", "-r", "clinic", "-q", "clientId=web"))[0];
  expect(web.publicClient).toBe(true);
  expect(web.attributes["pkce.code.challenge.method"]).toBe("S256");
  const api = JSON.parse(kcadm("get", "clients", "-r", "clinic", "-q", "clientId=records-api"))[0];
  expect(api.bearerOnly).toBe(true);
});

test("a pod and the browser's port-forward see the same issuer", async () => {
  const fromPod = execFileSync("kubectl", [...KUBECTL, "-n", "clinic", "exec", "deploy/records-api", "--", "python", "-c",
    "import json,urllib.request;print(json.load(urllib.request.urlopen('http://keycloak.keycloak.svc:8080/realms/clinic/.well-known/openid-configuration'))['issuer'])"],
    { encoding: "utf8" }).trim();
  expect(fromPod).toBe(ISSUER);

  const pf: ChildProcess = spawn("kubectl", [...KUBECTL, "-n", "keycloak", "port-forward", "svc/keycloak", "8180:8080"], { stdio: "ignore" });
  try {
    let issuer = "";
    for (let i = 0; i < 20 && !issuer; i++) {
      await new Promise((r) => setTimeout(r, 500));
      issuer = await fetch(`${ISSUER}/.well-known/openid-configuration`).then((r) => r.json()).then((j) => j.issuer).catch(() => "");
    }
    expect(issuer).toBe(ISSUER);
  } finally {
    pf.kill();
  }
});

test("make keycloak can run twice", () => {
  execFileSync("sh", [resolve(ROOT, "scripts/keycloak-configure.sh")], { encoding: "utf8" });
});
