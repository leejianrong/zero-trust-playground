import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";

// V5: External Secrets Operator copies one static secret from Vault into a Kubernetes Secret, and follows changes.
const KUBECTL = ["--context", "k3d-ztp"];

const vaultPut = (value: string) =>
  execFileSync("kubectl", [...KUBECTL, "-n", "vault", "exec", "deploy/vault", "--", "env", "VAULT_ADDR=http://127.0.0.1:8200",
    "VAULT_TOKEN=playground-dev-root", "vault", "kv", "put", "secret/clinic/billing-api-key", `value=${value}`]);

const synced = (): string => {
  try {
    const b64 = execFileSync("kubectl", [...KUBECTL, "-n", "clinic", "get", "secret", "billing-api-key", "-o", "jsonpath={.data.value}"],
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
    return Buffer.from(b64, "base64").toString();
  } catch {
    return "";
  }
};

test.afterAll(() => { vaultPut("placeholder-api-key"); });

test("a change in Vault reaches the Kubernetes Secret within 40 seconds", async () => {
  test.setTimeout(150_000);
  vaultPut("first-value");
  await expect.poll(synced, { timeout: 60_000, intervals: [2_000] }).toBe("first-value");
  const changed = `changed-${Date.now()}`;
  vaultPut(changed);
  await expect.poll(synced, { timeout: 40_000, intervals: [2_000] }).toBe(changed);
});
