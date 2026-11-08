import type { CronJob } from "../api";
import { ASK_STEPS, type AskPhase, isFinal, stepIndex } from "../ask";
import { t } from "../i18n";
import { truncate } from "../utils";

interface Props {
  prompt: string;
  phase: AskPhase;
  /** Furthest step seen so far; a failed question stops there. */
  reached: number;
  job: CronJob | null;
  slow: boolean;
  /** Polling stopped (maxWaitMin) before the job finished. */
  stale: boolean;
}

/** Where one question is: queued → answering → sent to the chat. */
export function AskProgress({ prompt, phase, reached, job, slow, stale }: Props) {
  const current = stepIndex(phase, reached);
  const final = isFinal(phase);
  const error = phase === "failed" ? String(job?.last_error ?? "").trim() : "";

  return (
    <div className="card ask-progress" aria-live="polite">
      <p className="ask-question">{truncate(prompt, 160)}</p>
      <ol className="ask-steps" aria-label={t("ask.progress")}>
        {ASK_STEPS.map((step, i) => {
          let state = "todo";
          if (i < current || (i === current && phase === "delivered")) state = "done";
          else if (i === current && phase === "failed") state = "failed";
          else if (i === current && !final) state = "active";
          return (
            <li key={step} className={`ask-step ${state}`} aria-current={state === "active" ? "step" : undefined}>
              <span className="ask-step-dot" aria-hidden="true" />
              <span className="ask-step-label">{t(`ask.step.${step}`)}</span>
            </li>
          );
        })}
      </ol>
      <p className={`ask-status ${phase}`}>{t(`ask.status.${phase}`)}</p>
      {error && <p className="ask-note">{truncate(error, 200)}</p>}
      {!final && (slow || stale) && <p className="ask-note">{t(stale ? "ask.stale" : "ask.slow")}</p>}
    </div>
  );
}
