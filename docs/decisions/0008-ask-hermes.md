# 0008. Ask Hermes is a one-shot cron job delivered to an admin's chat

Status: Accepted.

## Context

The Send tab forwards text to the owner's chat with the bot, where the Hermes gateway picks it up as an ordinary
message. That works, but the Mini App never knows what happened to it. An "Ask" box was proposed: type a question in
the panel, and the agent's answer arrives in the Telegram chat, with the panel showing that it is running.

Hermes already has a primitive with exactly that shape: a cron job. Hermes v0.23.0 accepts an ISO timestamp as a
one-shot schedule, `repeat=1`, and a delivery target of `telegram:<chat id>`. Its own cron ticker (in the gateway)
claims the due job, runs one agent turn and hands the answer to the Telegram delivery queue. The panel already lists
cron jobs with a `running` flag.

Before writing the route we checked that path against real Hermes v0.23.0: `create_job(schedule=<now>, repeat=1,
deliver="telegram:<id>")`, then `cron.scheduler.tick()`, with only the agent turn (`run_job`) and the Telegram send
(`cron.delivery_queue.enqueue`) replaced. The job ran once, the answer was queued for that chat, and the job ended
`completed`. `deliver="telegram"` alone resolves to Hermes's home channel and to nothing when that is unset, so the
route names the chat explicitly.

## Decision

- `POST /ask` (`plugin/dashboard/routes_ask.py`) takes `prompt` and, optionally, `chat_id`. Any other field is
  refused (422). It creates an agent cron job: schedule = now (UTC, ISO 8601), `repeat=1`,
  `deliver="telegram:<chat id>"`, name `Ask: <first words of the prompt>`.
- The client cannot set `script`, `no_agent`, `workdir`, `model`, `provider`, toolsets, schedule or delivery. An Ask
  can do nothing that `POST /cron` cannot already do, and less.
- `chat_id` must be on the plugin-owned admin list (0007) and defaults to the first admin, the same rule as the send
  box. An empty admin list answers 400.
- Limits are plugin settings, not code: `ask_max_chars` (default 2000, accepted 1-20000) caps the prompt;
  `ask_max_pending` (default 1, accepted 1-10) caps how many Asks may wait or run at once, answering 409 `busy`
  beyond it. A value outside its range falls back to the default with a warning.
- Auth is the same as every other route: the dashboard session token from the Telegram login (0001, 0006). No
  new public path, no new token route.
- `tests/contract/test_hermes_real.py::test_ask_once_job_delivers_to_telegram` keeps the measured path above under
  CI for every Hermes release in `compat/hermes-versions.json`; `tests/test_ask.py` covers the limits.

## Consequences

- Answers need the Hermes gateway running (it runs the cron ticker) with Telegram configured, as any cron delivery
  does. Without it the Ask waits as a scheduled job and blocks the next one; it can be deleted from the Cron tab.
- Asks appear in the Cron tab and in Hermes's own `hermes cron list` like any other one-shot job.

## Undo

Remove `routes_ask` from `_ROUTE_MODULES` in `plugin/dashboard/plugin_api.py` (or revert the commit). Nothing is
stored outside Hermes's own cron store; finished Ask jobs stay there as completed one-shot jobs.
