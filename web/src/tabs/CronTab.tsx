import { useEffect, useState } from "react";
import {
  Capabilities,
  CronJob,
  cronAction,
  cronCancel,
  cronCreate,
  CronCreatePayload,
  cronDelete,
  cronUpdate,
  getCapabilities,
  getCron,
  NO_CAPABILITIES,
} from "../api";
import { cancelNotice, canStop, catchUpInitial, catchUpToSend, CRON_TEXT, formBusy, warningsText } from "../cron";
import { CronForm, EMPTY_FORM, FormState } from "./CronForm";
import "../cron.css";
import { formatRelative, formatWhen, scheduleInput, scheduleLabel, toEpochSeconds, truncate } from "../utils";
import { ErrorBox, Loading, PullToRefresh, SectionTitle, tgHaptic, tgHapticImpact } from "../components";

export function CronTab() {
  const [jobs, setJobs] = useState<CronJob[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [caps, setCaps] = useState<Capabilities>(NO_CAPABILITIES);
  const [notice, setNotice] = useState<string | null>(null);
  // catch_up as loaded into the form, so an untouched switch is not sent.
  const [catchUpStart, setCatchUpStart] = useState<boolean | null>(null);

  const refresh = async () => {
    try {
      const r = await getCron();
      setJobs(r.jobs);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  };

  useEffect(() => {
    refresh();
    getCapabilities().then(setCaps);
  }, []);

  const act = async (id: string, action: "pause" | "resume" | "trigger") => {
    setNotice(null);
    setBusy(id + "/" + action);
    try {
      await cronAction(id, action);
      await refresh();
      tgHaptic("success");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      tgHaptic("error");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (job: CronJob) => {
    const ok = window.confirm(
      `Delete cron job "${job.name ?? job.id}"? This is permanent.`,
    );
    if (!ok) return;
    setBusy(job.id + "/delete");
    try {
      await cronDelete(job.id);
      await refresh();
      tgHaptic("success");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      tgHaptic("error");
    } finally {
      setBusy(null);
    }
  };

  const stop = async (job: CronJob) => {
    const name = job.name ?? job.id;
    tgHaptic("warning");
    if (!window.confirm(CRON_TEXT.stopConfirm(name))) return;
    setNotice(null);
    setBusy(job.id + "/cancel");
    try {
      const r = await cronCancel(job.id);
      setNotice(cancelNotice(r, name));
      await refresh();
      tgHaptic("success");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      tgHaptic("error");
    } finally {
      setBusy(null);
    }
  };

  const startCreate = () => {
    setEditId(null);
    setForm(EMPTY_FORM);
    setCatchUpStart(null);
    setFormError(null);
    setShowForm(true);
    tgHapticImpact("light");
  };

  const startEdit = (job: CronJob) => {
    setEditId(job.id);
    setForm({
      name: job.name ?? "",
      schedule: scheduleInput(job),
      prompt: String(job.prompt ?? ""),
      deliver: String(job.deliver ?? "telegram"),
      catch_up: catchUpInitial(job),
    });
    setCatchUpStart(catchUpInitial(job));
    setFormError(null);
    setShowForm(true);
    tgHapticImpact("light");
  };

  const cancelForm = () => {
    setShowForm(false);
    setEditId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const submitForm = async () => {
    if (!form.schedule.trim()) {
      setFormError("Schedule is required (e.g. 30m, 0 9 * * *)");
      return;
    }
    if (!form.prompt.trim()) {
      setFormError("Prompt is required");
      return;
    }
    setFormError(null);
    setNotice(null);
    setBusy(editId ?? "new");
    const catchUp = catchUpToSend(caps, catchUpStart, form.catch_up);
    try {
      let warnings: string[] | undefined;
      if (editId) {
        const r = await cronUpdate(editId, {
          name: form.name.trim() || undefined,
          schedule: form.schedule.trim(),
          prompt: form.prompt.trim(),
          deliver: form.deliver,
          ...(catchUp !== undefined ? { catch_up: catchUp } : {}),
        });
        warnings = r?.warnings;
      } else {
        const payload: CronCreatePayload = {
          name: form.name.trim() || undefined,
          schedule: form.schedule.trim(),
          prompt: form.prompt.trim(),
          deliver: form.deliver,
          ...(typeof catchUp === "boolean" ? { catch_up: catchUp } : {}),
        };
        warnings = (await cronCreate(payload))?.warnings;
      }
      await refresh();
      const warned = warningsText(warnings);
      setNotice(warned);
      tgHaptic(warned ? "warning" : "success");
      cancelForm();
    } catch (e) {
      setFormError(String((e as Error).message ?? e));
      tgHaptic("error");
    } finally {
      setBusy(null);
    }
  };

  if (error && !jobs) return <ErrorBox msg={error} />;
  if (!jobs) return <Loading />;

  return (
    <PullToRefresh onRefresh={refresh}>
      <div className="section-title-row">
        <SectionTitle>Scheduled jobs</SectionTitle>
        <button
          type="button"
          className="ghost-btn"
          onClick={startCreate}
          aria-label="Create cron job"
        >
          + New
        </button>
      </div>

      {error && <ErrorBox msg={error} />}
      {notice && (
        <div className="cron-notice" role="status">
          {notice}
        </div>
      )}

      {showForm && (
        <CronForm
          form={form}
          editing={!!editId}
          formError={formError}
          busy={formBusy(busy, editId)}
          showCatchUp={caps.cron_catch_up}
          onChange={setForm}
          onCancel={cancelForm}
          onSubmit={submitForm}
        />
      )}

      {jobs.length === 0 && (
        <div className="empty">No cron jobs scheduled. Tap “+ New”.</div>
      )}

      {jobs.map((j) => {
        const enabled = j.enabled !== false;
        const acting = busy?.startsWith(j.id + "/");
        const nextRun = toEpochSeconds(j.next_run_at ?? j.next_run);
        const lastRun = toEpochSeconds(j.last_run_at ?? j.last_run);
        const failed = /fail|error/i.test(String(j.last_status ?? ""));
        const running = j.running === true;
        const stoppable = canStop(j, caps);
        const badge = running
          ? { cls: "badge running", text: CRON_TEXT.badgeRunning }
          : !enabled
            ? { cls: "badge paused", text: "paused" }
            : failed
              ? { cls: "badge failed", text: "last run failed" }
              : { cls: "badge", text: "active" };
        return (
          <div key={j.id} className="cron-row">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span className="name">{j.name ?? j.id}</span>
              <span className={badge.cls}>{badge.text}</span>
            </div>
            <div className="meta">
              <span>{scheduleLabel(j)}</span>
              {enabled && nextRun && <span>next {formatWhen(nextRun)}</span>}
              {lastRun && <span>last {formatRelative(lastRun)}</span>}
            </div>
            {j.prompt && (
              <div className="item-preview" style={{ marginTop: 4 }}>
                {truncate(String(j.prompt), 100)}
              </div>
            )}
            <div className="actions">
              {stoppable && (
                <button
                  className="btn-secondary danger cron-stop"
                  disabled={acting}
                  aria-busy={busy === j.id + "/cancel"}
                  onClick={() => stop(j)}
                >
                  {busy === j.id + "/cancel" ? CRON_TEXT.stopping : CRON_TEXT.stop}
                </button>
              )}
              {enabled ? (
                <button
                  className="btn-secondary"
                  disabled={acting}
                  onClick={() => act(j.id, "pause")}
                >
                  Pause
                </button>
              ) : (
                <button
                  className="btn-secondary"
                  disabled={acting}
                  onClick={() => act(j.id, "resume")}
                >
                  Resume
                </button>
              )}
              <button
                className="btn-secondary"
                disabled={acting}
                onClick={() => act(j.id, "trigger")}
              >
                Run now
              </button>
              <button
                className="btn-secondary"
                disabled={acting}
                onClick={() => startEdit(j)}
              >
                Edit
              </button>
              <button
                className="btn-secondary danger"
                disabled={acting}
                onClick={() => remove(j)}
              >
                Delete
              </button>
            </div>
          </div>
        );
      })}
    </PullToRefresh>
  );
}
