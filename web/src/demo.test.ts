import { describe, expect, it } from "vitest";
import { handleDemoRequest } from "./demo";
import type { SessionRow } from "./api";

// The Usage card filters sessions by rolling windows. A sample session sitting on a
// window edge flips in and out of the total from one render to the next, so README
// screenshots of Status and Usage disagree. Keep every sample row clear of the edges.
const WINDOWS_SEC = [1, 7, 30].map((d) => d * 86400);
const MARGIN_SEC = 30 * 60;

describe("demo sample sessions", () => {
  it("stay clear of the usage window edges", async () => {
    const { sessions } = (await handleDemoRequest("/sessions?limit=100")) as { sessions: SessionRow[] };
    const nowSec = Date.now() / 1000;
    expect(sessions.length).toBeGreaterThan(0);
    for (const s of sessions) {
      const age = nowSec - (s.last_active ?? 0);
      for (const w of WINDOWS_SEC) expect(Math.abs(age - w), `${s.id} vs ${w}s window`).toBeGreaterThan(MARGIN_SEC);
    }
  });

  it("gives the same Today total on repeated reads", async () => {
    const a = (await handleDemoRequest("/usage?window=today")) as { estimated_cost_usd: number };
    const b = (await handleDemoRequest("/usage?window=today")) as { estimated_cost_usd: number };
    expect(b.estimated_cost_usd).toBe(a.estimated_cost_usd);
  });
});
