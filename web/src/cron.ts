/**
 * Cron tab logic that does not need React: what to offer for a job, what to
 * send for "Run missed jobs", and how to word server answers.
 *
 * User-facing words live in the language files under `cron.*`.
 */

import type { Capabilities, CronCancelResp, CronJob } from "./api";
import { t } from "./i18n";

/** Stop is offered only for a run in flight, and only when Hermes can stop it. */
export function canStop(job: CronJob, caps: Capabilities): boolean {
  return caps.cron_cancel && job.running === true;
}

/** Form value: true/false = explicit choice, null = Hermes default. */
export function catchUpInitial(job?: CronJob | null): boolean | null {
  const v = job?.catch_up;
  return typeof v === "boolean" ? v : null;
}

/**
 * What to send for catch_up, or undefined to leave it out of the request.
 * Nothing is sent when Hermes lacks the feature or the user did not change it,
 * so saving a job never pins the global default by accident.
 */
export function catchUpToSend(
  caps: Capabilities,
  initial: boolean | null,
  current: boolean | null,
): boolean | null | undefined {
  if (!caps.cron_catch_up || current === initial) return undefined;
  return current;
}

export function warningsText(codes: string[] | undefined): string | null {
  if (!codes?.length) return null;
  return codes
    .map((c) => {
      const key = `cron.warning.${c}`;
      const text = t(key);
      return text === key ? t("cron.warningFallback", { code: c }) : text;
    })
    .join(" ");
}

export function cancelNotice(resp: CronCancelResp, name: string): string {
  return t(resp.action === "cancelled" ? "cron.stopped" : "cron.stopIdle", { name });
}

/**
 * Whether the open form is saving. `busy` holds the key of the action in
 * flight ("new", a job id, or "<id>/<action>"); with no edit open, a bare
 * `busy === editId` would compare null with null and lock a new form.
 */
export function formBusy(busy: string | null, editId: string | null): boolean {
  if (busy === null) return false;
  return busy === (editId ?? "new");
}
