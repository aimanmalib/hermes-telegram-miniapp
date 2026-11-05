import { tgHapticImpact, ToggleRow } from "../components";
import { t } from "../i18n";

export const SCHEDULE_PRESETS: { label: string; value: string }[] = [
  { label: "Every 30m", value: "30m" },
  { label: "Hourly", value: "1h" },
  { label: "Every 6h", value: "6h" },
  { label: "Daily 9am", value: "0 9 * * *" },
  { label: "Daily 9pm", value: "0 21 * * *" },
  { label: "Weekdays 8am", value: "0 8 * * 1-5" },
  { label: "Mondays 9am", value: "0 9 * * 1" },
];

const DELIVER_PRESETS = ["origin", "telegram", "local"];

export interface FormState {
  name: string;
  schedule: string;
  prompt: string;
  deliver: string;
  /** true/false = explicit choice; null = Hermes default (cron.catch_up_missed). */
  catch_up: boolean | null;
}

export const EMPTY_FORM: FormState = {
  name: "",
  schedule: "",
  prompt: "",
  deliver: "telegram",
  catch_up: null,
};

export function CronForm({
  form,
  editing,
  formError,
  busy,
  showCatchUp,
  onChange,
  onCancel,
  onSubmit,
}: {
  form: FormState;
  editing: boolean;
  formError: string | null;
  busy: boolean;
  /** Hermes stores a per-job catch_up (``capabilities.cron_catch_up``). */
  showCatchUp: boolean;
  onChange: (next: FormState) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="cron-form">
      <div className="form-title">
        {editing ? "Edit cron job" : "New cron job"}
      </div>

      <label className="field">
        <span>Name (optional)</span>
        <input
          type="text"
          value={form.name}
          onChange={(e) => onChange({ ...form, name: e.target.value })}
          placeholder="e.g. Morning briefing"
        />
      </label>

      <label className="field">
        <span>Schedule</span>
        <input
          type="text"
          value={form.schedule}
          onChange={(e) => onChange({ ...form, schedule: e.target.value })}
          placeholder="30m, 1h, 0 9 * * *, 2026-06-01T09:00"
        />
        <div className="chips" style={{ padding: "8px 0 0", marginLeft: 0 }}>
          {SCHEDULE_PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              className="chip"
              onClick={() => {
                onChange({ ...form, schedule: p.value });
                tgHapticImpact("light");
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </label>

      <label className="field">
        <span>Prompt</span>
        <textarea
          value={form.prompt}
          onChange={(e) => onChange({ ...form, prompt: e.target.value })}
          rows={4}
          placeholder="What should Hermes do when this fires?"
        />
      </label>

      <label className="field">
        <span>Deliver to</span>
        <div className="filter-pills">
          {DELIVER_PRESETS.map((d) => (
            <button
              key={d}
              type="button"
              data-active={form.deliver === d}
              className="filter-pill"
              onClick={() => {
                onChange({ ...form, deliver: d });
                tgHapticImpact("light");
              }}
            >
              {d}
            </button>
          ))}
        </div>
      </label>

      {showCatchUp && (
        <ToggleRow
          label={t("cron.catchUpLabel")}
          hint={
            form.catch_up === null
              ? t("cron.catchUpDefault")
              : form.catch_up
                ? t("cron.catchUpOn")
                : t("cron.catchUpOff")
          }
          checked={form.catch_up === true}
          disabled={busy}
          onChange={(v) => {
            onChange({ ...form, catch_up: v });
            tgHapticImpact("light");
          }}
        />
      )}

      {formError && (
        <p
          className="label"
          style={{ marginTop: 8, color: "var(--tg-destructive)" }}
        >
          {formError}
        </p>
      )}

      <div className="actions">
        <button
          type="button"
          className="btn-secondary"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
        <button
          type="button"
          className="btn-primary"
          onClick={onSubmit}
          disabled={busy}
        >
          {busy ? (editing ? "Saving…" : "Creating…") : editing ? "Save" : "Create"}
        </button>
      </div>
    </div>
  );
}
