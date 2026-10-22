/**
 * API client for /api/plugins/telegram-app/* endpoints.
 *
 * Auth flow:
 *   1. Call ``loginWithInitData(initData)`` once on mount.
 *   2. Server validates initData (HMAC primary, Ed25519 fallback) and
 *      returns the dashboard session token.
 *   3. We cache the token in memory and send it as ``X-Hermes-Session-Token``
 *      on every subsequent call.
 *   4. If a call returns 401 (process restarted, token rotated), we
 *      re-login transparently and retry the original call once.
 *
 * For local development with the Vite dev server (no Telegram), set
 * ``localStorage.devSessionToken`` to the dashboard token. Production builds
 * ignore it.
 *
 * Demo builds (``npm run build:demo`` / ``?demo=1`` on the dev server) answer
 * every call from ./demo.ts and never touch the network.
 */

import { getInitData } from "./telegram";
import { DEMO_ENABLED, demoRequest, DEMO_USER } from "./demo-gate";

const API_BASE = "/api/plugins/telegram-app";

let cachedToken: string | null = null;
let lastUser: AuthUser | null = null;

export interface AuthUser {
  id: number;
  first_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
}

export interface AuthResponse {
  ok: boolean;
  session_token?: string;
  user?: AuthUser;
  reason?: string;
}

function devToken(): string | null {
  if (!import.meta.env.DEV) return null;
  try {
    return localStorage.getItem("devSessionToken");
  } catch {
    return null;
  }
}

export function getCachedToken(): string | null {
  return cachedToken ?? devToken();
}

export function getLastUser(): AuthUser | null {
  return lastUser;
}

export async function loginWithInitData(initData?: string): Promise<AuthResponse> {
  if (DEMO_ENABLED) {
    lastUser = DEMO_USER;
    return { ok: true, user: DEMO_USER, reason: "demo" };
  }
  const data = initData ?? getInitData();
  if (!data) {
    // Dev shortcut — some browsers can't fake initData. If devToken is set
    // we count that as already-authed.
    const tok = devToken();
    if (tok) {
      cachedToken = tok;
      return { ok: true, session_token: tok, reason: "dev_token" };
    }
    return { ok: false, reason: "no_init_data" };
  }
  const res = await fetch(`${API_BASE}/auth/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: data }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`auth/verify ${res.status}: ${text}`);
  }
  const body: AuthResponse = await res.json();
  if (body.ok && body.session_token) {
    cachedToken = body.session_token;
    lastUser = body.user ?? null;
  }
  return body;
}

async function rawFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getCachedToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (token) headers["X-Hermes-Session-Token"] = token;
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  if (DEMO_ENABLED) return (await demoRequest(path, init)) as T;
  let res = await rawFetch(path, init);
  if (res.status === 401) {
    // Token expired — try to re-login from initData and retry once.
    const auth = await loginWithInitData();
    if (auth.ok) {
      res = await rawFetch(path, init);
    }
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} ${res.status}: ${text}`);
  }
  // Some endpoints return 204
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.includes("application/json")) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

// ---- typed wrappers ------------------------------------------------------

export interface SystemStatus {
  cpu_pct: number;
  mem_pct: number;
  mem_used_gb: number;
  mem_total_gb: number;
  load_avg: number[];
  disk_pct: number;
  disk_used_gb: number;
  disk_total_gb: number;
  sessions_count: number;
  cron_count: number;
  uptime_sec: number;
}

export const getStatus = () => api<SystemStatus>("/status");

export interface SessionRow {
  id: string;
  title: string;
  preview: string;
  source: string;
  model: string;
  started_at: number | null;
  last_active: number | null;
  message_count: number | null;
  tool_call_count: number | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface SessionsResp {
  sessions: SessionRow[];
}

export const getSessions = (limit = 30, source?: string) =>
  api<SessionsResp>(
    `/sessions?limit=${limit}${source ? `&source=${encodeURIComponent(source)}` : ""}`,
  );

export interface SessionMessage {
  role: string;
  content: string | null;
  name?: string;
  timestamp?: number;
}

export const getSessionMessages = (id: string, limit = 100) =>
  api<{ session_id: string; messages: SessionMessage[] }>(
    `/sessions/${encodeURIComponent(id)}/messages?limit=${limit}`,
  );

export interface CronSchedule {
  kind?: string;
  expr?: string;
  display?: string;
  run_at?: string;
  minutes?: number;
  [k: string]: unknown;
}

/** Shape of ``cron.jobs.list_jobs()`` in current Hermes (older builds used numeric next_run/last_run). */
export interface CronJob {
  id: string;
  name?: string | null;
  schedule?: CronSchedule | string;
  schedule_display?: string;
  prompt?: string | null;
  deliver?: string | null;
  enabled?: boolean;
  state?: string;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
  next_run?: number;
  last_run?: number;
  [k: string]: unknown;
}

export const getCron = () => api<{ jobs: CronJob[] }>("/cron");

export const cronAction = (id: string, action: "pause" | "resume" | "trigger") =>
  api<{ ok: boolean; id: string; action: string }>(`/cron/${encodeURIComponent(id)}/${action}`, {
    method: "POST",
  });

/** Agent jobs only; the plugin rejects script-only jobs and workdir. */
export interface CronCreatePayload {
  prompt: string;
  schedule: string;
  name?: string;
  deliver?: string;
  repeat?: number;
  skills?: string[];
  enabled_toolsets?: string[];
  model?: string;
  provider?: string;
}

export const cronCreate = (payload: CronCreatePayload) =>
  api<{ ok: boolean; job: CronJob }>("/cron", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export interface CronUpdatePayload {
  name?: string;
  schedule?: string;
  prompt?: string;
  deliver?: string;
  repeat?: number;
  skills?: string[];
  enabled_toolsets?: string[];
}

export const cronUpdate = (id: string, payload: CronUpdatePayload) =>
  api<{ ok: boolean; job: CronJob }>(`/cron/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const cronDelete = (id: string) =>
  api<{ ok: boolean; id: string; action: string }>(`/cron/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const sendCommand = (text: string) =>
  api<{ ok: boolean; message_id: number }>("/command", {
    method: "POST",
    body: JSON.stringify({ text }),
  });

export type LogFile = "agent" | "errors" | "gateway";
export type LogLevel = "ALL" | "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";

export interface LogsResponse {
  file: LogFile;
  level: LogLevel;
  lines: string[];
  count: number;
  mtime: number;
  path: string;
}

export const getLogs = (
  file: LogFile = "agent",
  lines = 200,
  level: LogLevel = "ALL",
) =>
  api<LogsResponse>(
    `/logs?file=${file}&lines=${lines}&level=${level}`,
  );

// ---- Usage / cost --------------------------------------------------------

export type UsageWindow = "today" | "week" | "month" | "all";

export interface UsageTopSession {
  id: string;
  title: string;
  source: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  message_count: number;
  last_active: number | null;
}

export interface UsageSummary {
  window: UsageWindow;
  session_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  message_count: number;
  top_sessions: UsageTopSession[];
  as_of: number;
}

export const getUsage = (window: UsageWindow = "today", top = 5) =>
  api<UsageSummary>(`/usage?window=${window}&top=${top}`);

// ---- Skills + memory ----------------------------------------------------

export interface SkillRow {
  id: string;
  name: string;
  description: string;
  category: string | null;
  size: number;
  path: string;
}

export interface SkillsListResp {
  skills: SkillRow[];
  count: number;
  root: string;
}

export interface SkillDetail {
  id: string;
  content: string;
  size: number;
  path: string;
}

export const getSkills = () => api<SkillsListResp>("/skills");

export const getSkill = (id: string) =>
  api<SkillDetail>(`/skills/${encodeURI(id)}`);

export interface MemoryFile {
  exists: boolean;
  content: string;
  size: number;
  mtime: number;
  path?: string;
}

export interface MemoryDump {
  root: string;
  files: {
    memory: MemoryFile;
    user: MemoryFile;
  };
}

export const getMemory = () => api<MemoryDump>("/memory");

// ---- Push alerts --------------------------------------------------------

export interface AlertsSettings {
  cron_failures: boolean;
  error_log: boolean;
  cost_threshold: boolean;
  cost_daily_usd: number;
  error_throttle_sec: number;
  poll_interval_sec: number;
}

export interface AlertsStatus {
  settings: AlertsSettings;
  running: boolean;
  last_tick: number | null;
  last_alert_at: number | null;
  last_alert_kind: string | null;
  errors_emitted_today: number;
  cron_failures_seen: number;
  state_path: string;
  has_bot_token: boolean;
  has_owner_chat: boolean;
}

export const getAlerts = () => api<AlertsStatus>("/alerts");

export const updateAlerts = (patch: Partial<AlertsSettings>) =>
  api<AlertsStatus>("/alerts", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

export const testAlert = () =>
  api<{ ok: boolean; sent: boolean; reason?: string }>("/alerts/test", {
    method: "POST",
  });
