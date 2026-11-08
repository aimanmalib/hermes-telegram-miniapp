import { describe, expect, it } from "vitest";
import CONFIG from "./config.json";
import { dailySpend, gaugeLevel, peakDay, type SpendRow } from "./spend";
import { sparklinePoints, VIEW } from "./Sparkline";

const STATUS_TAB = import.meta.glob("./tabs/StatusTab.tsx", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

const BANDS = { warnPct: 60, critPct: 85 };
const DAY = 86_400_000;
// Noon local time, so "n days ago" never crosses a midnight boundary by accident.
const NOW = new Date(2026, 10, 8, 12, 0, 0).getTime();
const at = (daysAgo: number, usd: number): SpendRow => ({
  last_active: (NOW - daysAgo * DAY) / 1000,
  started_at: null,
  estimated_cost_usd: usd,
});

describe("gauge colour bands", () => {
  it("maps a percentage to ok / warn / crit at the band edges", () => {
    expect(gaugeLevel(0, BANDS)).toBe("ok");
    expect(gaugeLevel(59.9, BANDS)).toBe("ok");
    expect(gaugeLevel(60, BANDS)).toBe("warn");
    expect(gaugeLevel(84.9, BANDS)).toBe("warn");
    expect(gaugeLevel(85, BANDS)).toBe("crit");
    expect(gaugeLevel(120, BANDS)).toBe("crit");
  });

  it("reads its default bands from config.json", () => {
    const { warnPct, critPct } = CONFIG.gauges;
    expect(warnPct).toBeLessThan(critPct);
    expect(gaugeLevel(warnPct - 0.1)).toBe("ok");
    expect(gaugeLevel(warnPct)).toBe("warn");
    expect(gaugeLevel(critPct)).toBe("crit");
  });

  it("keeps the thresholds out of the Status tab", () => {
    const src = Object.values(STATUS_TAB)[0];
    expect(src).toContain("gaugeLevel(");
    expect(src).not.toMatch(/pct\s*>=\s*\d/);
  });
});

describe("daily spend series", () => {
  it("returns one zero slot per day, oldest first, when there is no data", () => {
    const s = dailySpend([], 7, NOW);
    expect(s).toHaveLength(7);
    expect(s.every((d) => d.usd === 0)).toBe(true);
    expect(s[6].day).toBe(new Date(2026, 10, 8).getTime());
    expect(s[0].day).toBe(new Date(2026, 10, 2).getTime());
    expect(peakDay(s)).toBeNull();
  });

  it("puts a single session on its last-active day", () => {
    const s = dailySpend([at(2, 0.5)], 7, NOW);
    expect(s.map((d) => d.usd)).toEqual([0, 0, 0, 0, 0.5, 0, 0]);
    expect(peakDay(s)).toEqual({ index: 4, usd: 0.5 });
  });

  it("sums sessions per day across seven days and drops older or future rows", () => {
    const rows = [0, 1, 2, 3, 4, 5, 6].map((d) => at(d, d + 1));
    rows.push(at(0, 1), at(7, 99), at(-1, 99));
    const s = dailySpend(rows, 7, NOW);
    expect(s.map((d) => d.usd)).toEqual([7, 6, 5, 4, 3, 2, 2]);
    expect(peakDay(s)).toEqual({ index: 0, usd: 7 });
  });

  it("falls back to started_at and ignores rows without a time", () => {
    const rows: SpendRow[] = [
      { last_active: null, started_at: NOW / 1000, estimated_cost_usd: 0.25 },
      { last_active: null, started_at: null, estimated_cost_usd: 5 },
    ];
    expect(dailySpend(rows, 3, NOW).map((d) => d.usd)).toEqual([0, 0, 0.25]);
  });

  it("uses the configured number of days", () => {
    expect(CONFIG.spendTrend.days).toBeGreaterThan(0);
    expect(dailySpend([], CONFIG.spendTrend.days, NOW)).toHaveLength(CONFIG.spendTrend.days);
  });
});

describe("sparkline geometry", () => {
  const base = VIEW.height - VIEW.pad;

  it("draws nothing for no values", () => {
    expect(sparklinePoints([])).toEqual([]);
  });

  it("centres a single value", () => {
    expect(sparklinePoints([3])).toEqual([{ x: VIEW.width / 2, y: VIEW.pad }]);
    expect(sparklinePoints([0])).toEqual([{ x: VIEW.width / 2, y: base }]);
  });

  it("spreads seven values edge to edge with zero on the baseline", () => {
    const pts = sparklinePoints([0, 1, 2, 4, 2, 1, 0]);
    expect(pts).toHaveLength(7);
    expect(pts[0].x).toBe(0);
    expect(pts[6].x).toBeCloseTo(VIEW.width);
    expect(pts[0].y).toBe(base);
    expect(pts[3].y).toBe(VIEW.pad);
    expect(pts[1].y).toBeCloseTo(base - (base - VIEW.pad) / 4);
  });

  it("keeps an all-zero week flat on the baseline", () => {
    expect(sparklinePoints([0, 0, 0, 0, 0, 0, 0]).every((p) => p.y === base)).toBe(true);
  });
});
