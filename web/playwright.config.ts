import { defineConfig } from "@playwright/test";

// Needs the cluster up with the echo workloads: `make up && make echo`.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    { command: "make -C .. observer", url: "http://localhost:8765/healthz", reuseExistingServer: true },
    { command: "npm run dev -- --port 5173 --strictPort", url: "http://localhost:5173", reuseExistingServer: true },
  ],
});
