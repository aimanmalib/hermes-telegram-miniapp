/**
 * Cron tab logic that does not need React: what to offer for a job, what to
 * send for "Run missed jobs", and how to word server answers.
 *
 * The user-facing strings for the Stop / catch-up features live in CRON_TEXT
 * so the i18n pass can move them to the language files in one place.
 */

import type { Capabilities, CronCancelResp, CronJob } from "./api";

export const CRON_TEXT = {
  badgeRunning: "running",
  stop: "Stop",
  stopping: "Stopping…",
  stopConfirm: (name: string) =>
    `Stop the run of "${name}" that is in progress? The schedule stays as it is.`,
  stopped: (name: string) => `Stopped "${name}".`,
  stopIdle: (name: string) => `"${name}" had already finished; nothing to stop.`,
  catchUpLabel: "Run missed jobs",
  catchUpOn: "If Hermes was down at a scheduled time, run the job once when it is back.",
  catchUpOff: "Skip runs that were missed while Hermes was down.",
  catchUpDefault: "Not set: Hermes uses its global setting.",
  warnings: {
    catch_up_unsupported:
      "This Hermes cannot store “Run missed jobs”; the job was saved without it.",
  } as Record<string, string>,
  warningFallback: (code: string) => `Saved with a warning: ${code}`,
};

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
  return codes.map((c) => CRON_TEXT.warnings[c] ?? CRON_TEXT.warningFallback(c)).join(" ");
}

export function cancelNotice(resp: CronCancelResp, name: string): string {
  return resp.action === "cancelled" ? CRON_TEXT.stopped(name) : CRON_TEXT.stopIdle(name);
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
