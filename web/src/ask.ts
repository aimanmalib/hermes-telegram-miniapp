/**
 * Ask tab logic that does not need React: where a question is on its way to
 * the chat, read from the one-shot cron job Hermes keeps for it (see
 * docs/decisions/0008-ask-hermes.md), and when the tab stops checking.
 *
 * Timings live in config.json under `ask`; words live under `ask.*`.
 */

import type { CronJob } from "./api";
import config from "./config.json";

export type AskPhase = "queued" | "running" | "delivered" | "failed" | "gone";

/** The steps drawn in the progress track, in order. */
export const ASK_STEPS = ["queued", "running", "delivered"] as const;

const FAILED = /fail|error|cancel/i;
const DONE_STATES = new Set(["completed"]);

/** One job (or none, when it was deleted) → the phase shown to the user. */
export function askPhase(job: CronJob | undefined | null): AskPhase {
  if (!job) return "gone";
  if (job.running === true) return "running";
  const status = String(job.last_status ?? "");
  const state = String(job.state ?? "");
  if (FAILED.test(status) || FAILED.test(state) || job.last_error) return "failed";
  if (DONE_STATES.has(state) || (status !== "" && job.last_run_at)) return "delivered";
  return "queued";
}

/** Phases after which the job will not change any more. */
export function isFinal(phase: AskPhase): boolean {
  return phase === "delivered" || phase === "failed" || phase === "gone";
}

/** Index of the phase in ASK_STEPS; failed/gone stop at the step they reached. */
export function stepIndex(phase: AskPhase, reached: number): number {
  const i = (ASK_STEPS as readonly string[]).indexOf(phase);
  return i >= 0 ? i : reached;
}

export interface AskTiming {
  pollSec: number;
  slowSec: number;
  maxWaitMin: number;
}

export const ASK_TIMING: AskTiming = config.ask;

/** Show the "is the gateway running?" hint once a question has waited this long. */
export function isSlow(startedMs: number, nowMs: number, timing: AskTiming = ASK_TIMING): boolean {
  return nowMs - startedMs >= timing.slowSec * 1000;
}

/** Stop polling after maxWaitMin; the job itself stays in the Cron tab. */
export function shouldPoll(phase: AskPhase, startedMs: number, nowMs: number, timing: AskTiming = ASK_TIMING): boolean {
  return !isFinal(phase) && nowMs - startedMs < timing.maxWaitMin * 60_000;
}
