/**
 * SAMPLE data for demo mode. Everything here is invented; nothing is read
 * from a Hermes server. Loaded only when demo-gate.ts enables demo mode.
 */

import type {
  AlertsStatus,
  CronJob,
  LogFile,
  LogsResponse,
  MemoryDump,
  SessionMessage,
  SessionRow,
  SkillDetail,
  SkillsListResp,
  SystemStatus,
  UsageSummary,
  UsageWindow,
} from "./api";

const now = () => Date.now() / 1000;
const iso = (offsetSec: number) => new Date((now() + offsetSec) * 1000).toISOString();

function sessions(): SessionRow[] {
  const t = now();
  const row = (
    id: string,
    title: string,
    preview: string,
    source: string,
    model: string,
    agoMin: number,
    messages: number,
    tools: number,
    inTok: number,
    outTok: number,
    cost: number,
  ): SessionRow => ({
    id,
    title,
    preview,
    source,
    model,
    started_at: t - agoMin * 60 - 1800,
    last_active: t - agoMin * 60,
    message_count: messages,
    tool_call_count: tools,
    input_tokens: inTok,
    output_tokens: outTok,
    estimated_cost_usd: cost,
  });
  return [
    row("s-7f3a", "Morning briefing", "Three meetings today; the deploy window moved to 15:00.", "cron", "claude-sonnet-4-5", 4, 6, 3, 18_400, 1_250, 0.07),
    row("s-6c21", "Fix flaky checkout test", "The race was in the payment mock; added an await and the suite is green.", "telegram", "claude-opus-4-1", 38, 42, 27, 412_000, 18_900, 1.84),
    row("s-5b90", "Summarise support inbox", "12 new tickets, 2 need a reply today (refund, login loop).", "telegram", "claude-sonnet-4-5", 95, 14, 6, 61_300, 4_100, 0.24),
    row("s-4e18", "Draft release notes v2.3", "Grouped 19 merged PRs into Features, Fixes and Internal.", "cli", "claude-sonnet-4-5", 180, 22, 9, 133_000, 9_800, 0.55),
    row("s-3d07", "Disk usage check", "/ is at 47%. Largest growth: docker build cache (+2.1 GB).", "cron", "claude-haiku-4-5", 260, 4, 2, 7_900, 610, 0.01),
    row("s-2a66", "Research: SQLite WAL backups", "Use the online backup API or VACUUM INTO; copying the file alone misses the -wal.", "telegram", "claude-opus-4-1", 1440, 31, 14, 288_000, 12_400, 1.21),
    row("s-19c4", "Weekly metrics digest", "Signups +8% week over week; churn flat.", "cron", "claude-sonnet-4-5", 2900, 8, 4, 22_000, 2_300, 0.09),
  ];
}

function status(): SystemStatus {
  const wobble = Math.sin(now() / 7) * 3;
  return {
    cpu_pct: Math.round((18 + wobble) * 10) / 10,
    mem_pct: 61.4,
    mem_used_gb: 4.91,
    mem_total_gb: 8,
    load_avg: [0.42, 0.55, 0.61],
    disk_pct: 47.2,
    disk_used_gb: 75.5,
    disk_total_gb: 160,
    sessions_count: 214,
    cron_count: 4,
    uptime_sec: 3 * 86400 + 5 * 3600 + 12 * 60,
  };
}

function usage(window: UsageWindow): UsageSummary {
  const all = sessions();
  const span = { today: 1, week: 7, month: 30, all: 3650 }[window] * 86400;
  const rows = all.filter((s) => (s.last_active ?? 0) >= now() - span);
  const sum = (f: (s: SessionRow) => number) => rows.reduce((a, s) => a + f(s), 0);
  const top = [...rows]
    .sort((a, b) => b.estimated_cost_usd - a.estimated_cost_usd)
    .slice(0, 5)
    .map((s) => ({
      id: s.id,
      title: s.title,
      source: s.source,
      model: s.model,
      input_tokens: s.input_tokens,
      output_tokens: s.output_tokens,
      estimated_cost_usd: s.estimated_cost_usd,
      message_count: s.message_count ?? 0,
      last_active: s.last_active,
    }));
  return {
    window,
    session_count: rows.length,
    input_tokens: sum((s) => s.input_tokens),
    output_tokens: sum((s) => s.output_tokens),
    total_tokens: sum((s) => s.input_tokens + s.output_tokens),
    estimated_cost_usd: Math.round(sum((s) => s.estimated_cost_usd) * 100) / 100,
    message_count: sum((s) => s.message_count ?? 0),
    top_sessions: top,
    as_of: now(),
  };
}

let cronJobs: CronJob[] | null = null;

function cron(): CronJob[] {
  if (cronJobs) return cronJobs;
  cronJobs = [
    {
      id: "a1b2c3",
      name: "Morning briefing",
      schedule: { kind: "cron", expr: "0 8 * * 1-5", display: "0 8 * * 1-5" },
      schedule_display: "0 8 * * 1-5",
      prompt: "Summarise my calendar, unread email and anything that broke overnight.",
      deliver: "telegram",
      enabled: true,
      next_run_at: iso(14 * 3600),
      last_run_at: iso(-4 * 60),
      last_status: "ok",
    },
    {
      id: "d4e5f6",
      name: "Disk usage check",
      schedule: { kind: "interval", minutes: 360, display: "every 6h" },
      schedule_display: "every 6h",
      prompt: "Report disk usage and the three fastest-growing directories.",
      deliver: "telegram",
      enabled: true,
      next_run_at: iso(95 * 60),
      last_run_at: iso(-260 * 60),
      last_status: "ok",
    },
    {
      id: "g7h8i9",
      name: "Weekly metrics digest",
      schedule: { kind: "cron", expr: "0 9 * * 1", display: "0 9 * * 1" },
      schedule_display: "0 9 * * 1",
      prompt: "Pull signups, churn and revenue for the past week and compare with the week before.",
      deliver: "telegram",
      enabled: true,
      next_run_at: iso(4 * 86400),
      last_run_at: iso(-2 * 86400),
      last_status: "delivery_failed",
      last_error: "Telegram: chat not found",
    },
    {
      id: "j0k1l2",
      name: "Backup restore drill",
      schedule: { kind: "cron", expr: "30 3 * * 0", display: "30 3 * * 0" },
      schedule_display: "30 3 * * 0",
      prompt: "Restore last night's backup into a scratch directory and verify row counts.",
      deliver: "local",
      enabled: false,
      state: "paused",
      next_run_at: null,
      last_run_at: iso(-9 * 86400),
      last_status: "ok",
    },
  ];
  return cronJobs;
}

const LOG_LINES: Record<LogFile, string[]> = {
  agent: [
    "INFO - hermes.gateway - telegram: update 88213 from user 1 (text, 42 chars)",
    "INFO - hermes.agent - session s-7f3a: tool web_search (0.8s)",
    "INFO - hermes.agent - session s-7f3a: tool calendar.list_events (0.3s)",
    "DEBUG - hermes.state - wal checkpoint: 12 pages",
    "INFO - hermes.cron - job a1b2c3 'Morning briefing' finished ok in 21.4s",
    "WARNING - hermes.providers - rate limited by provider, retrying in 2s",
    "INFO - hermes.agent - session s-6c21: tool terminal (exit 0, 14.2s)",
    "INFO - hermes.agent - session s-6c21: tool file_edit tests/checkout.spec.ts",
    "ERROR - hermes.cron - job g7h8i9 delivery failed: Telegram: chat not found",
    "INFO - hermes.gateway - telegram: sent reply (3 messages)",
    "INFO - hermes.plugin.telegram-app - mini app login ok",
  ],
  errors: [
    "WARNING - hermes.providers - rate limited by provider, retrying in 2s",
    "ERROR - hermes.cron - job g7h8i9 delivery failed: Telegram: chat not found",
    "WARNING - hermes.tools - web_fetch: 403 from example.org, falling back to search",
  ],
  gateway: [
    "INFO - hermes.gateway - telegram: polling started",
    "INFO - hermes.gateway - telegram: update 88212 from user 1 (voice, 7s)",
    "INFO - hermes.gateway - telegram: update 88213 from user 1 (text, 42 chars)",
    "INFO - hermes.gateway - telegram: sent reply (3 messages)",
  ],
};

function logs(path: string): LogsResponse {
  const q = new URLSearchParams(path.split("?")[1] ?? "");
  const file = (q.get("file") as LogFile) || "agent";
  const level = (q.get("level") || "ALL").toUpperCase();
  const rank: Record<string, number> = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };
  const min = level === "ALL" ? 0 : rank[level] ?? 0;
  const base = new Date();
  const lines = (LOG_LINES[file] ?? [])
    .map((l, i) => {
      const ts = new Date(base.getTime() - (LOG_LINES[file].length - i) * 47_000);
      const stamp = ts.toISOString().replace("T", " ").slice(0, 23).replace(".", ",");
      return `${stamp} - ${l}`;
    })
    .filter((l) => {
      const lv = Object.keys(rank).find((k) => l.includes(` ${k} - `)) ?? "INFO";
      return rank[lv] >= min;
    });
  return {
    file,
    level: level as LogsResponse["level"],
    lines,
    count: lines.length,
    mtime: now() - 20,
    path: `~/.hermes/logs/${file}.log`,
  };
}

const SKILLS: SkillsListResp = {
  root: "~/.hermes/skills",
  count: 6,
  skills: [
    { id: "devops/disk-report", name: "disk-report", description: "Summarise disk usage and growth by directory.", category: "devops", size: 2140, path: "" },
    { id: "devops/restore-drill", name: "restore-drill", description: "Restore a backup to a scratch dir and verify it.", category: "devops", size: 3310, path: "" },
    { id: "writing/release-notes", name: "release-notes", description: "Group merged PRs into user-facing release notes.", category: "writing", size: 1870, path: "" },
    { id: "writing/briefing", name: "briefing", description: "Morning briefing from calendar, inbox and alerts.", category: "writing", size: 2650, path: "" },
    { id: "research/paper-digest", name: "paper-digest", description: "Read a paper and produce a one-page digest.", category: "research", size: 1520, path: "" },
    { id: "support/inbox-triage", name: "inbox-triage", description: "Sort support email by urgency and draft replies.", category: "support", size: 2980, path: "" },
  ].map((s) => ({ ...s, path: `~/.hermes/skills/${s.id}/SKILL.md` })),
};

function skill(id: string): SkillDetail {
  const meta = SKILLS.skills.find((s) => s.id === id) ?? SKILLS.skills[0];
  const content = `---\nname: ${meta.name}\ndescription: ${meta.description}\n---\n\n# ${meta.name}\n\nSample skill text shown in demo mode.\n\n1. Gather the inputs.\n2. Do the work with the available tools.\n3. Reply with a short summary and links.\n`;
  return { id: meta.id, content, size: content.length, path: meta.path };
}

const MEMORY: MemoryDump = {
  root: "~/.hermes/memories",
  files: {
    memory: {
      exists: true,
      content:
        "- Deploys happen from the main branch after CI is green.\n- Backups run nightly at 03:17 and are copied off-site.\n- Prefer short Telegram replies; long output goes to a file.\n",
      size: 176,
      mtime: now() - 3 * 3600,
      path: "~/.hermes/memories/MEMORY.md",
    },
    user: {
      exists: true,
      content: "- Timezone: UTC+8.\n- Likes bullet summaries with the decision first.\n",
      size: 72,
      mtime: now() - 26 * 3600,
      path: "~/.hermes/memories/USER.md",
    },
  },
};

const MESSAGES: SessionMessage[] = [
  { role: "user", content: "The checkout test fails about one run in five. Can you find out why?" },
  { role: "assistant", content: "I'll run it in a loop and capture the failures first." },
  { role: "tool", name: "terminal", content: "for i in $(seq 20); do npm test -- checkout; done\n4 of 20 runs failed: expected 'paid', got 'pending'" },
  { role: "assistant", content: "The payment mock resolves after the assertion in 4/20 runs. The handler is missing an await on confirmPayment(). Fixing it now." },
  { role: "tool", name: "file_edit", content: "tests/checkout.spec.ts: 1 line changed" },
  { role: "assistant", content: "Fixed. 50 consecutive runs pass. Want me to open a PR?" },
];

let alerts: AlertsStatus = {
  settings: {
    cron_failures: true,
    error_log: false,
    cost_threshold: true,
    cost_daily_usd: 5,
    error_throttle_sec: 300,
    poll_interval_sec: 30,
  },
  running: true,
  last_tick: now() - 12,
  last_alert_at: now() - 2 * 86400,
  last_alert_kind: "cron",
  errors_emitted_today: 0,
  cron_failures_seen: 1,
  state_path: "~/.hermes/state/telegram-app/alerts_state.json",
  has_bot_token: true,
  has_owner_chat: true,
};

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function handleDemoRequest(path: string, init: RequestInit = {}): Promise<unknown> {
  await delay(120);
  const method = (init.method ?? "GET").toUpperCase();
  const [route, query = ""] = path.split("?");
  const q = new URLSearchParams(query);

  if (route === "/status") return status();
  if (route === "/usage") return usage((q.get("window") as UsageWindow) || "today");
  if (route === "/sessions") return { sessions: sessions().slice(0, Number(q.get("limit") || 30)) };
  if (/^\/sessions\/[^/]+\/messages$/.test(route)) {
    const t = now() - 40 * 60;
    return {
      session_id: decodeURIComponent(route.split("/")[2]),
      messages: MESSAGES.map((m, i) => ({ ...m, timestamp: t + i * 70 })),
    };
  }
  if (route === "/cron" && method === "GET") return { jobs: cron() };
  if (route === "/cron" && method === "POST") {
    const body = JSON.parse(String(init.body ?? "{}"));
    const job: CronJob = {
      id: Math.random().toString(16).slice(2, 8),
      name: body.name ?? null,
      schedule: { kind: "cron", expr: body.schedule, display: body.schedule },
      schedule_display: body.schedule,
      prompt: body.prompt,
      deliver: body.deliver,
      enabled: true,
      next_run_at: iso(3600),
      last_run_at: null,
      last_status: null,
    };
    cron().unshift(job);
    return { ok: true, job };
  }
  const cronMatch = route.match(/^\/cron\/([^/]+)(?:\/(pause|resume|trigger))?$/);
  if (cronMatch) {
    const id = decodeURIComponent(cronMatch[1]);
    const job = cron().find((j) => j.id === id);
    if (!job) throw new Error(`${path} 404: job not found`);
    const action = cronMatch[2];
    if (action === "pause") job.enabled = false;
    if (action === "resume") job.enabled = true;
    if (action === "trigger") {
      job.last_run_at = iso(0);
      job.last_status = "ok";
    }
    if (method === "PATCH") Object.assign(job, JSON.parse(String(init.body ?? "{}")));
    if (method === "DELETE") cronJobs = cron().filter((j) => j.id !== id);
    return { ok: true, id, action: action ?? method.toLowerCase(), job };
  }
  if (route === "/logs") return logs(path);
  if (route === "/skills") return SKILLS;
  if (route.startsWith("/skills/")) return skill(decodeURI(route.slice("/skills/".length)));
  if (route === "/memory") return MEMORY;
  if (route === "/alerts" && method === "GET") return alerts;
  if (route === "/alerts" && method === "PATCH") {
    alerts = { ...alerts, settings: { ...alerts.settings, ...JSON.parse(String(init.body ?? "{}")) } };
    return alerts;
  }
  if (route === "/alerts/test") return { ok: true, sent: false, reason: "demo mode: nothing is sent" };
  if (route === "/command") return { ok: true, message_id: 0 };
  throw new Error(`${path} 404: not available in demo mode`);
}
