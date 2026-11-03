import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
  server: { proxy: Object.fromEntries(["/events", "/layers", "/healthz", "/app", "/links"].map((p) => [p, "http://localhost:8765"])) },
  test: { include: ["src/**/*.test.ts"] },
});
