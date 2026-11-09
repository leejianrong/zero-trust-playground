import { execFileSync } from "node:child_process";
import { defineConfig } from "@playwright/test";

// The Headlamp forward waits for a ready pod, so only start it when Headlamp is running. Without it a run that
// does not touch Headlamp (the matrix, say) would sit out the 60 second server timeout and fail.
const headlampRunning = (() => {
  try {
    const ready = execFileSync("kubectl", ["--context", "k3d-ztp", "-n", "headlamp", "get", "deploy", "headlamp",
      "-o", "jsonpath={.status.readyReplicas}"], { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
    return Number(ready) > 0;
  } catch {
    return false;
  }
})();

// `kubectl port-forward` dies when its pod goes away or the stream resets (the e2e runs have shown ECONNRESET mid-suite).
// Run it in a loop so a drop costs a second, and pipe its output so the log says when and why it happened.
const forward = (ns: string, target: string, ports: string) => ({
  command: `bash -c 'while true; do kubectl --context k3d-ztp -n ${ns} port-forward ${target} ${ports} || echo "port-forward ${target} exited ($?), restarting"; sleep 1; done'`,
  stdout: "pipe" as const,
  stderr: "pipe" as const,
});

// Needs the cluster up with the echo workloads: `make up && make echo`.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  // A shared CI runner is slow to render the first rows; the default 5 seconds failed two different tests in two runs.
  expect: { timeout: 15_000 },
  workers: 1, // tests share one cluster, and one of them removes a registration
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    { command: "make -C .. observer", url: "http://localhost:8765/healthz", reuseExistingServer: true },
    // The clinic app itself, as a user would open it.
    { ...forward("clinic", "svc/web", "8081:8080"), url: "http://localhost:8081/healthz", reuseExistingServer: true },
    // Keycloak, where the clinic page sends the browser to sign in.
    { ...forward("keycloak", "svc/keycloak", "8180:8080"), url: "http://localhost:8180/realms/clinic", reuseExistingServer: true },
    ...(headlampRunning
      ? [{ ...forward("headlamp", "svc/headlamp", "4466:80"), url: "http://localhost:4466", reuseExistingServer: true }]
      : []),
    { command: "npm run dev -- --port 5173 --strictPort", url: "http://localhost:5173", reuseExistingServer: true },
  ],
});
