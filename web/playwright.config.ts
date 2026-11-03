import { defineConfig } from "@playwright/test";

// Needs the cluster up with the echo workloads: `make up && make echo`.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  workers: 1, // tests share one cluster, and one of them removes a registration
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    { command: "make -C .. observer", url: "http://localhost:8765/healthz", reuseExistingServer: true },
    // The clinic app itself, as a user would open it.
    { command: "kubectl --context k3d-ztp -n clinic port-forward svc/web 8081:8080", url: "http://localhost:8081/healthz", reuseExistingServer: true },
    { command: "kubectl --context k3d-ztp -n headlamp port-forward svc/headlamp 4466:80", url: "http://localhost:4466", reuseExistingServer: true },
    { command: "npm run dev -- --port 5173 --strictPort", url: "http://localhost:5173", reuseExistingServer: true },
  ],
});
