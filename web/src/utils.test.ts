import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  formatBytes,
  formatRelative,
  formatTokens,
  formatUptime,
  formatUsd,
  formatWhen,
  scheduleInput,
  scheduleLabel,
  toEpochSeconds,
  truncate,
} from "./utils";

const NOW = Date.UTC(2026, 9, 22, 9, 0, 0);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe("formatters", () => {
  it("formats bytes, tokens, money and uptime", () => {
    expect(formatBytes(4.91)).toBe("4.9 GB");
    expect(formatBytes(0.5)).toBe("512 MB");
    expect(formatTokens(999)).toBe("999");
    expect(formatTokens(18_400)).toBe("18.4k");
    expect(formatTokens(2_500_000)).toBe("2.50M");
    expect(formatUsd(0)).toBe("$0");
    expect(formatUsd(0.004)).toBe("<$0.01");
    expect(formatUsd(1.844)).toBe("$1.84");
    expect(formatUptime(3 * 86400 + 5 * 3600 + 12 * 60)).toBe("3d 5h");
    expect(formatUptime(30)).toBe("<1m");
    expect(formatUptime(2 * 3600)).toBe("2h 0m");
  });

  it("formats relative past and future times", () => {
    const t = NOW / 1000;
    expect(formatRelative(t - 30)).toBe("30s ago");
    expect(formatRelative(t - 3 * 3600)).toBe("3h ago");
    expect(formatRelative(null)).toBe("—");
    expect(formatWhen(t + 95 * 60)).toBe("in 2h");
    expect(formatWhen(t + 10 * 60)).toBe("in 10m");
    expect(formatWhen(t - 120)).toBe("2m ago");
  });

  it("truncates with an ellipsis", () => {
    expect(truncate("hello world", 5)).toBe("hell…");
    expect(truncate("hi", 5)).toBe("hi");
    expect(truncate(null, 5)).toBe("");
  });
});

describe("toEpochSeconds", () => {
  it("accepts ISO strings (current Hermes cron) and unix seconds (legacy)", () => {
    expect(toEpochSeconds("2026-10-22T09:00:00+00:00")).toBe(NOW / 1000);
    expect(toEpochSeconds("2026-10-22T09:00:00Z")).toBe(NOW / 1000);
    expect(toEpochSeconds(1_700_000_000)).toBe(1_700_000_000);
    expect(toEpochSeconds("1700000000")).toBe(1_700_000_000);
  });

  it("returns null for missing or garbage values", () => {
    for (const v of [null, undefined, "", "soon", 0, -5, NaN, {}]) {
      expect(toEpochSeconds(v)).toBeNull();
    }
  });
});

describe("schedule helpers", () => {
  it("never renders an object (current Hermes stores schedule as a dict)", () => {
    const job = { schedule: { kind: "cron", expr: "0 9 * * *" } };
    expect(scheduleLabel(job)).toBe("0 9 * * *");
    expect(scheduleLabel({ ...job, schedule_display: "weekdays 9am" })).toBe("weekdays 9am");
    expect(scheduleLabel({ schedule: "30m" })).toBe("30m");
    expect(scheduleLabel({})).toBe("—");
  });

  it("pre-fills an editable expression", () => {
    expect(scheduleInput({ schedule: { kind: "cron", expr: "0 9 * * 1", display: "Mondays" } })).toBe("0 9 * * 1");
    expect(scheduleInput({ schedule: { kind: "interval", minutes: 30, display: "every 30m" } })).toBe("every 30m");
    expect(scheduleInput({ schedule: { kind: "once", run_at: "2026-11-01T09:00:00", display: "once at …" } })).toBe(
      "2026-11-01T09:00:00",
    );
    expect(scheduleInput({ schedule: "1h" })).toBe("1h");
  });
});
