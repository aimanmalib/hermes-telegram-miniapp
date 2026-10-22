/**
 * Demo mode switch.
 *
 * Demo mode renders every tab from built-in SAMPLE data and makes no API
 * calls. It exists for screenshots and for trying the UI without a Hermes
 * server. It can only be on in two cases:
 *
 *   1. a demo build: `npm run build:demo` (Vite mode "demo", output in
 *      `../dist-demo/`, never the `dist/` that install.sh deploys), or
 *   2. the Vite dev server with `?demo=1` in the URL.
 *
 * A normal production build (`npm run build`) compiles `__DEMO_BUILD__` to
 * `false` and `import.meta.env.DEV` to `false`, so DEMO_ENABLED is a constant
 * `false` and the demo module is dropped from the bundle entirely
 * (`npm run check:no-demo` verifies that). The UI always shows a "Demo data"
 * banner while demo mode is on.
 */

import type { AuthUser } from "./api";

declare const __DEMO_BUILD__: boolean;

function urlAsksForDemo(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("demo") === "1";
  } catch {
    return false;
  }
}

export const DEMO_ENABLED: boolean =
  __DEMO_BUILD__ || (import.meta.env.DEV && urlAsksForDemo());

export const DEMO_USER: AuthUser = { id: 1, first_name: "Demo", username: "demo" };

export async function demoRequest(path: string, init: RequestInit = {}): Promise<unknown> {
  const { handleDemoRequest } = await import("./demo");
  return handleDemoRequest(path, init);
}
