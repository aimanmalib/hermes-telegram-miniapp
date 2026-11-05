/**
 * Format helpers — file sizes, timestamps, etc. No deps.
 * Words come from the language files (i18n); numbers and dates use Intl.
 */

import { fmtDate, fmtNumber, t } from "./i18n";

export function formatBytes(gb: number): string {
  if (gb >= 1) return `${fmtNumber(gb, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;
  return `${fmtNumber(Math.round(gb * 1024))} MB`;
}

export function formatRelative(ts: number | null | undefined): string {
  if (!ts) return "—";
  const ms = ts * 1000;
  const diff = Date.now() - ms;
  if (diff < 0) return t("fmt.now");
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return t("fmt.secAgo", { n: sec });
  const min = Math.floor(sec / 60);
  if (min < 60) return t("fmt.minAgo", { n: min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return t("fmt.hrAgo", { n: hr });
  const day = Math.floor(hr / 24);
  if (day < 7) return t("fmt.dayAgo", { n: day });
  return fmtDate(ms);
}

export function formatUptime(sec: number): string {
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const parts: string[] = [];
  if (d) parts.push(t("fmt.dur.d", { n: d }));
  if (h) parts.push(t("fmt.dur.h", { n: h }));
  if (!d && (m || h)) parts.push(t("fmt.dur.m", { n: m }));
  return parts.join(" ") || t("fmt.dur.lt1m");
}

export function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

export function formatUsd(n: number): string {
  if (!n) return "$0";
  if (n < 0.01) return `<$0.01`;
  return `$${n.toFixed(2)}`;
}

export function truncate(s: string | null | undefined, n: number): string {
  if (!s) return "";
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

/**
 * Normalise a timestamp to unix seconds. Hermes cron stores ISO-8601 strings
 * (``next_run_at`` / ``last_run_at``); sessions use unix seconds.
 * Returns null for anything unparseable.
 */
export function toEpochSeconds(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) && v > 0 ? v : null;
  if (typeof v === "string" && v.trim()) {
    const n = Number(v);
    if (Number.isFinite(n)) return n > 0 ? n : null;
    const ms = Date.parse(v);
    return Number.isNaN(ms) ? null : ms / 1000;
  }
  return null;
}

/** Relative time, but also says "in 5m" for future instants (cron next run). */
export function formatWhen(ts: number | null | undefined): string {
  if (!ts) return "—";
  const diff = ts * 1000 - Date.now();
  if (diff <= 0) return formatRelative(ts);
  const min = Math.round(diff / 60_000);
  if (min < 1) return t("fmt.inLt1m");
  if (min < 60) return t("fmt.inMin", { n: min });
  const hr = Math.round(min / 60);
  if (hr < 24) return t("fmt.inHr", { n: hr });
  return t("fmt.inDay", { n: Math.round(hr / 24) });
}

/** Human-readable cron schedule; current Hermes stores ``schedule`` as an object. */
export function scheduleLabel(job: {
  schedule?: unknown;
  schedule_display?: unknown;
}): string {
  if (typeof job.schedule_display === "string" && job.schedule_display)
    return job.schedule_display;
  const s = job.schedule;
  if (typeof s === "string") return s;
  if (s && typeof s === "object") {
    const o = s as Record<string, unknown>;
    for (const k of ["display", "expr", "value", "kind"]) {
      if (typeof o[k] === "string" && o[k]) return o[k] as string;
    }
  }
  return "—";
}

/** The schedule string to pre-fill when editing (an expression Hermes can parse). */
export function scheduleInput(job: { schedule?: unknown; schedule_display?: unknown }): string {
  const s = job.schedule;
  if (typeof s === "string") return s;
  if (s && typeof s === "object") {
    const o = s as Record<string, unknown>;
    if (typeof o.expr === "string") return o.expr;
    if (o.kind === "once" && typeof o.run_at === "string") return o.run_at;
    if (typeof o.display === "string") return o.display;
  }
  return typeof job.schedule_display === "string" ? job.schedule_display : "";
}
