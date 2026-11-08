import { useEffect, useState } from "react";
import {
  AlertsSettings,
  AlertsStatus,
  getAlerts,
  getStatus,
  getUsage,
  SystemStatus,
  testAlert,
  updateAlerts,
  UsageSummary,
  UsageWindow,
} from "../api";
import {
  formatBytes,
  formatTokens,
  formatUptime,
  formatUsd,
  truncate,
} from "../utils";
import { ErrorBox, LangSwitch, Loading, SectionTitle, tgHapticImpact, ToggleRow } from "../components";
import { fmtNumber, t } from "../i18n";
import { errorText } from "../errors";
import { gaugeLevel } from "../spend";
import { SpendTrend } from "./SpendTrend";
import "../status.css";

const WINDOWS: UsageWindow[] = ["today", "week", "month", "all"];

export function StatusTab({
  onOpenSession,
}: {
  onOpenSession: (id: string, title: string) => void;
}) {
  const [data, setData] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [window, setWindow] = useState<UsageWindow>("today");

  // ---- System gauges (5s poll) -----------------------------------
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await getStatus();
        if (!cancelled) setData(s);
      } catch (e) {
        if (!cancelled) setError(errorText(e));
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // ---- Usage (refresh on window change + every 60s) --------------
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const u = await getUsage(window, 5);
        if (!cancelled) setUsage(u);
      } catch (e) {
        if (!cancelled) setUsageError(errorText(e));
      }
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [window]);

  if (error) return <ErrorBox msg={error} />;
  if (!data) return <Loading />;

  return (
    <>
      <SectionTitle>{t("status.system")}</SectionTitle>
      <div className="gauges">
        <Gauge
          name={t("status.cpu")}
          pct={data.cpu_pct}
          sub={t("status.load", {
            values: data.load_avg
              .map((l) => fmtNumber(l, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
              .join(" "),
          })}
        />
        <Gauge
          name={t("status.memory")}
          pct={data.mem_pct}
          sub={`${formatBytes(data.mem_used_gb)} / ${formatBytes(data.mem_total_gb)}`}
        />
        <Gauge
          name={t("status.disk")}
          pct={data.disk_pct}
          sub={`${formatBytes(data.disk_used_gb)} / ${formatBytes(data.disk_total_gb)}`}
        />
        <Gauge name={t("status.uptime")} pct={null} sub={formatUptime(data.uptime_sec)} />
      </div>

      <SectionTitle>{t("status.hermes")}</SectionTitle>
      <div className="card group">
        <div className="row">
          <span className="label">{t("status.sessions")}</span>
          <span className="value">{fmtNumber(data.sessions_count)}</span>
        </div>
        <div className="row">
          <span className="label">{t("status.cronJobs")}</span>
          <span className="value">{fmtNumber(data.cron_count)}</span>
        </div>
      </div>

      {/* ---- Usage --------------------------------------------- */}
      <div className="section-title-row">
        <SectionTitle>{t("status.usage")}</SectionTitle>
        <div
          style={{
            display: "flex",
            gap: 4,
            marginLeft: "var(--space-4)",
            marginRight: "var(--space-4)",
          }}
        >
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              data-active={w === window}
              className="filter-pill"
              onClick={() => {
                setWindow(w);
                tgHapticImpact("light");
              }}
            >
              {t(`status.window.${w}`)}
            </button>
          ))}
        </div>
      </div>

      {usageError && <ErrorBox msg={usageError} />}
      {!usage && !usageError && <Loading />}
      {usage && (
        <>
          <div className="usage-grid">
            <UsageCard
              label={t("status.spend")}
              value={formatUsd(usage.estimated_cost_usd)}
              hint={t("status.sessionCount", { count: usage.session_count })}
              accent
            />
            <UsageCard
              label={t("status.tokens")}
              value={formatTokens(usage.total_tokens)}
              hint={t("status.tokensInOut", {
                in: formatTokens(usage.input_tokens),
                out: formatTokens(usage.output_tokens),
              })}
            />
            <UsageCard
              label={t("status.messages")}
              value={fmtNumber(usage.message_count)}
              hint={
                usage.session_count > 0
                  ? t("status.avgPerSession", {
                      avg: fmtNumber(usage.message_count / usage.session_count, {
                        minimumFractionDigits: 1,
                        maximumFractionDigits: 1,
                      }),
                    })
                  : "—"
              }
            />
          </div>

          <SpendTrend />

          {usage.top_sessions.length > 0 && (
            <>
              <div
                className="section-title"
                style={{
                  marginLeft: "calc(var(--space-4) + var(--space-1))",
                  marginTop: 0,
                }}
              >
                {t("status.topByCost")}
              </div>
              {usage.top_sessions.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="list-item tappable"
                  onClick={() => {
                    tgHapticImpact("light");
                    onOpenSession(s.id, s.title);
                  }}
                >
                  <div className="item-title">{truncate(s.title, 60)}</div>
                  <div className="item-meta">
                    <span className="src">{s.source ?? "?"}</span>
                    <span>{t("common.msgs", { count: s.message_count })}</span>
                    <span>
                      {formatTokens(s.input_tokens + s.output_tokens)}
                    </span>
                    <span style={{ marginLeft: "auto" }}>
                      {formatUsd(s.estimated_cost_usd)}
                    </span>
                  </div>
                </button>
              ))}
            </>
          )}
        </>
      )}

      <AlertsCard />

      <SectionTitle>{t("lang.title")}</SectionTitle>
      <div className="card group">
        <div className="row">
          <span className="label">{t("lang.label")}</span>
          <LangSwitch />
        </div>
      </div>
    </>
  );
}

function AlertsCard() {
  const [status, setStatus] = useState<AlertsStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [costInput, setCostInput] = useState("");

  const refresh = async () => {
    try {
      const s = await getAlerts();
      setStatus(s);
      setCostInput(String(s.settings.cost_daily_usd));
      setErr(null);
    } catch (e) {
      setErr(errorText(e));
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const toggle = async (key: keyof AlertsSettings, value: boolean) => {
    if (!status) return;
    setBusy(key);
    tgHapticImpact("light");
    try {
      const s = await updateAlerts({ [key]: value } as Partial<AlertsSettings>);
      setStatus(s);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const saveCost = async () => {
    const n = parseFloat(costInput);
    if (Number.isNaN(n) || n < 0) {
      setErr(t("alerts.invalidThreshold"));
      return;
    }
    setBusy("cost");
    tgHapticImpact("light");
    try {
      const s = await updateAlerts({ cost_daily_usd: n });
      setStatus(s);
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const sendTest = async () => {
    setBusy("test");
    setTestMsg(null);
    tgHapticImpact("medium");
    try {
      const r = await testAlert();
      setTestMsg(
        r.sent ? t("alerts.testSent") : t("alerts.testFailed", { reason: r.reason ?? t("common.unknown") }),
      );
    } catch (e) {
      setTestMsg(t("alerts.testFailed", { reason: errorText(e) }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <SectionTitle>{t("alerts.title")}</SectionTitle>
      {err && <ErrorBox msg={err} />}
      {!status && !err && <Loading />}
      {status && (
        <div className="alerts-card">
          {!status.has_bot_token || !status.has_owner_chat ? (
            <div className="alerts-warn">
              {t("alerts.notConfigured")}
            </div>
          ) : null}

          <ToggleRow
            label={t("alerts.cronFailures")}
            hint={t("alerts.cronFailuresHint")}
            checked={status.settings.cron_failures}
            disabled={busy === "cron_failures"}
            onChange={(v) => toggle("cron_failures", v)}
          />
          <ToggleRow
            label={t("alerts.errorLog")}
            hint={t("alerts.errorLogHint", { sec: status.settings.error_throttle_sec })}
            checked={status.settings.error_log}
            disabled={busy === "error_log"}
            onChange={(v) => toggle("error_log", v)}
          />
          <ToggleRow
            label={t("alerts.costThreshold")}
            hint={t("alerts.costThresholdHint", { usd: status.settings.cost_daily_usd })}
            checked={status.settings.cost_threshold}
            disabled={busy === "cost_threshold"}
            onChange={(v) => toggle("cost_threshold", v)}
          />

          <div className="alerts-row threshold">
            <span className="alerts-label">{t("alerts.thresholdLabel")}</span>
            <input
              type="number"
              inputMode="decimal"
              min={0}
              step="0.5"
              value={costInput}
              onChange={(e) => setCostInput(e.target.value)}
              className="alerts-input"
            />
            <button
              type="button"
              className="btn small"
              onClick={saveCost}
              disabled={busy === "cost"}
            >
              {t("common.save")}
            </button>
          </div>

          <div className="alerts-meta">
            <span>
              {t("alerts.watcher")}{" "}
              <b>{t(status.running ? "alerts.watcherRunning" : "alerts.watcherStopped")}</b>
            </span>
            {status.last_alert_kind && (
              <span>{t("alerts.last", { kind: status.last_alert_kind })}</span>
            )}
            <span>{t("alerts.errToday", { count: status.errors_emitted_today })}</span>
          </div>

          <div className="alerts-actions">
            <button
              type="button"
              className="btn"
              onClick={sendTest}
              disabled={busy === "test"}
            >
              {busy === "test" ? t("alerts.sending") : t("alerts.sendTest")}
            </button>
            <button
              type="button"
              className="btn ghost"
              onClick={refresh}
              disabled={busy !== null}
            >
              {t("common.refresh")}
            </button>
          </div>
          {testMsg && <div className="alerts-toast">{testMsg}</div>}
        </div>
      )}
    </>
  );
}

function UsageCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint: string;
  accent?: boolean;
}) {
  return (
    <div className={accent ? "usage-card accent" : "usage-card"}>
      <div className="name">{label}</div>
      <div className="big">{value}</div>
      <div className="sub">{hint}</div>
    </div>
  );
}

function Gauge({
  name,
  pct,
  sub,
}: {
  name: string;
  pct: number | null;
  sub: string;
}) {
  return (
    <div className="gauge" data-level={pct !== null ? gaugeLevel(pct) : undefined}>
      <div className="name">{name}</div>
      <div className="pct">{pct !== null ? `${pct.toFixed(0)}%` : sub}</div>
      {pct !== null && (
        <>
          <div className="sub">{sub}</div>
          <div className="bar">
            <div style={{ transform: `scaleX(${Math.min(Math.max(pct, 0), 100) / 100})` }} />
          </div>
        </>
      )}
    </div>
  );
}
