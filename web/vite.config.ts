import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svelte()],
  server: { proxy: { "/events": "http://localhost:8765", "/healthz": "http://localhost:8765" } },
  test: { include: ["src/**/*.test.ts"] },
});
