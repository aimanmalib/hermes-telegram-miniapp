/**
 * Status-tab math kept apart from React so it can be tested directly:
 * gauge colour bands and the daily spend series behind the sparkline.
 * Thresholds and the number of days live in config.json, not here.
 */
import CONFIG from "./config.json";

export type GaugeLevel = "ok" | "warn" | "crit";

export interface GaugeBands {
  warnPct: number;
  critPct: number;
}

export function gaugeLevel(pct: number, bands: GaugeBands = CONFIG.gauges): GaugeLevel {
  if (pct >= bands.critPct) return "crit";
  if (pct >= bands.warnPct) return "warn";
  return "ok";
}

export interface SpendRow {
  last_active: number | null;
  started_at: number | null;
  estimated_cost_usd: number;
}

export interface DaySpend {
  /** Local midnight of the day, in ms. */
  day: number;
  usd: number;
}

function localMidnight(ms: number): number {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/**
 * Spend per local day for the last `days` days, oldest first, today last.
 * A session counts on the day it was last active (the same rule the
 * /usage endpoint uses for its windows). Timestamps are epoch seconds.
 */
export function dailySpend(rows: SpendRow[], days: number, nowMs: number = Date.now()): DaySpend[] {
  if (days < 1) return [];
  const out: DaySpend[] = [];
  const today = localMidnight(nowMs);
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    out.push({ day: d.getTime(), usd: 0 });
  }
  const first = out[0].day;
  for (const r of rows) {
    const ts = Number(r.last_active ?? r.started_at ?? 0) * 1000;
    if (!Number.isFinite(ts) || ts < first || ts > nowMs) continue;
    const day = localMidnight(ts);
    const slot = out.find((s) => s.day === day);
    if (slot) slot.usd += Number(r.estimated_cost_usd) || 0;
  }
  return out;
}

export interface Peak {
  index: number;
  usd: number;
}

/** Highest day, or null when nothing was spent. Ties go to the latest day. */
export function peakDay(series: DaySpend[]): Peak | null {
  let best: Peak | null = null;
  series.forEach((s, index) => {
    if (s.usd > 0 && (!best || s.usd >= best.usd)) best = { index, usd: s.usd };
  });
  return best;
}
