import { describe, expect, it } from "vitest";
import type { CronJob } from "./api";
import { askPhase, isFinal, isSlow, shouldPoll, stepIndex } from "./ask";

const job = (extra: Partial<CronJob>): CronJob => ({ id: "a1", name: "Ask: hi", ...extra });
const timing = { pollSec: 3, slowSec: 45, maxWaitMin: 10 };

describe("askPhase", () => {
  it("reads a deleted job as gone", () => {
    expect(askPhase(undefined)).toBe("gone");
  });

  it("waits until the cron tick claims the job", () => {
    expect(askPhase(job({ state: "scheduled", last_status: null }))).toBe("queued");
  });

  it("follows the running flag", () => {
    expect(askPhase(job({ state: "scheduled", running: true }))).toBe("running");
  });

  it("is delivered once Hermes marks the one-shot job completed", () => {
    expect(askPhase(job({ state: "completed", last_status: "ok", last_run_at: "2026-11-09T00:00:00Z" }))).toBe(
      "delivered",
    );
    expect(askPhase(job({ state: "completed" }))).toBe("delivered");
  });

  it("flags a failed or cancelled run", () => {
    expect(askPhase(job({ state: "completed", last_status: "error" }))).toBe("failed");
    expect(askPhase(job({ last_status: "cancelled", last_run_at: "2026-11-09T00:00:00Z" }))).toBe("failed");
    expect(askPhase(job({ state: "scheduled", last_error: "model not found" }))).toBe("failed");
  });
});

describe("progress and polling", () => {
  it("keeps the step reached when a question fails", () => {
    expect(stepIndex("running", 0)).toBe(1);
    expect(stepIndex("failed", 1)).toBe(1);
    expect(isFinal("failed") && isFinal("gone") && isFinal("delivered")).toBe(true);
    expect(isFinal("queued") || isFinal("running")).toBe(false);
  });

  it("hints at the gateway after slowSec and stops polling after maxWaitMin", () => {
    expect(isSlow(0, 44_999, timing)).toBe(false);
    expect(isSlow(0, 45_000, timing)).toBe(true);
    expect(shouldPoll("queued", 0, 599_999, timing)).toBe(true);
    expect(shouldPoll("queued", 0, 600_000, timing)).toBe(false);
    expect(shouldPoll("delivered", 0, 1, timing)).toBe(false);
  });
});
