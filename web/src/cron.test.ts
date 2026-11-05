import { describe, expect, it } from "vitest";
import type { Capabilities, CronJob } from "./api";
import { cancelNotice, canStop, catchUpInitial, catchUpToSend, CRON_TEXT, formBusy, warningsText } from "./cron";

const ALL: Capabilities = { cron_cancel: true, cron_catch_up: true };
const NONE: Capabilities = { cron_cancel: false, cron_catch_up: false };
const job = (extra: Partial<CronJob> = {}): CronJob => ({ id: "j1", name: "Job", ...extra });

describe("canStop", () => {
  it("offers Stop only for a running job on a Hermes that can cancel", () => {
    expect(canStop(job({ running: true }), ALL)).toBe(true);
    expect(canStop(job({ running: true }), NONE)).toBe(false);
    expect(canStop(job({ running: false }), ALL)).toBe(false);
    expect(canStop(job(), ALL)).toBe(false);
  });
});

describe("catch_up form value", () => {
  it("reads explicit booleans and treats anything else as the Hermes default", () => {
    expect(catchUpInitial(job({ catch_up: true }))).toBe(true);
    expect(catchUpInitial(job({ catch_up: false }))).toBe(false);
    expect(catchUpInitial(job({ catch_up: null }))).toBeNull();
    expect(catchUpInitial(job())).toBeNull();
    expect(catchUpInitial(null)).toBeNull();
  });

  it("sends catch_up only when Hermes supports it and the user changed it", () => {
    expect(catchUpToSend(ALL, null, null)).toBeUndefined();
    expect(catchUpToSend(ALL, true, true)).toBeUndefined();
    expect(catchUpToSend(ALL, null, true)).toBe(true);
    expect(catchUpToSend(ALL, true, false)).toBe(false);
    expect(catchUpToSend(NONE, null, true)).toBeUndefined();
  });
});

describe("formBusy", () => {
  it("leaves a new job form usable while nothing is saving", () => {
    // Regression: `busy === editId` was null === null, so Cancel/Create stayed disabled.
    expect(formBusy(null, null)).toBe(false);
    expect(formBusy(null, "j1")).toBe(false);
  });

  it("is busy only for the save of the form that is open", () => {
    expect(formBusy("new", null)).toBe(true);
    expect(formBusy("j1", "j1")).toBe(true);
    expect(formBusy("j2", "j1")).toBe(false);
    expect(formBusy("new", "j1")).toBe(false);
    expect(formBusy("j1/pause", null)).toBe(false);
  });
});

describe("server answers", () => {
  it("words a stopped run and a run that had already finished differently", () => {
    const stopped = cancelNotice({ ok: true, id: "j1", action: "cancelled", cancelled: true }, "Job");
    const idle = cancelNotice({ ok: true, id: "j1", action: "idle", cancelled: false }, "Job");
    expect(stopped).toBe(CRON_TEXT.stopped("Job"));
    expect(idle).toBe(CRON_TEXT.stopIdle("Job"));
    expect(stopped).not.toBe(idle);
  });

  it("maps warning codes to text and keeps unknown codes visible", () => {
    expect(warningsText(undefined)).toBeNull();
    expect(warningsText([])).toBeNull();
    expect(warningsText(["catch_up_unsupported"])).toBe(CRON_TEXT.warnings.catch_up_unsupported);
    expect(warningsText(["new_code"])).toContain("new_code");
  });
});

describe("demo data", () => {
  it("has a running job that Stop ends, and a second Stop reports idle", async () => {
    const demo = await import("./demo");
    const health = (await demo.handleDemoRequest("/health")) as { capabilities: Capabilities };
    expect(health.capabilities).toEqual(ALL);
    const { jobs } = (await demo.handleDemoRequest("/cron")) as { jobs: CronJob[] };
    const running = jobs.filter((j) => j.running === true);
    expect(running).toHaveLength(1);
    const path = `/cron/${running[0].id}/cancel`;
    expect(await demo.handleDemoRequest(path, { method: "POST" })).toMatchObject({ action: "cancelled" });
    expect(await demo.handleDemoRequest(path, { method: "POST" })).toMatchObject({ action: "idle" });
  });
});
