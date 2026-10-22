/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Production build → ../dist (what scripts/install.sh deploys).
// Demo build (`--mode demo`) → ../dist-demo, with sample data compiled in.
// See src/demo-gate.ts for how demo mode is kept out of production.

/** In production builds, resolve ./demo to an empty stub so it is never bundled. */
function stripDemo(): Plugin {
  const stub = fileURLToPath(new URL("./src/demo-stub.ts", import.meta.url));
  return {
    name: "strip-demo",
    enforce: "pre",
    resolveId(source, importer) {
      if (source === "./demo" && importer?.replace(/\\/g, "/").endsWith("/src/demo-gate.ts")) {
        return stub;
      }
      return null;
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const demo = mode === "demo";
  return {
    plugins: [react(), ...(command === "build" && !demo ? [stripDemo()] : [])],
    base: "./",
    define: {
      __DEMO_BUILD__: JSON.stringify(demo),
    },
    build: {
      outDir: demo ? "../dist-demo" : "../dist",
      emptyOutDir: true,
      sourcemap: !demo,
    },
    server: {
      port: 5173,
      // Local dev: proxy the plugin API to a dashboard on loopback.
      proxy: {
        "/api": "http://127.0.0.1:9119",
      },
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
    },
  };
});
