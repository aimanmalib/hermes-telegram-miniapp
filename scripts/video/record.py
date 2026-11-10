# Record the demo video's screen clips against a running rig, and render its cards and frames.
#
#   uv run --with playwright==1.58.0 --with pillow python scripts/video/record.py
#
# Environment:
#   APP_URL      the Vite dev server (default http://127.0.0.1:5173); its /api proxy points at the rig
#   TOKEN_FILE   the rig's dashboard token (default $OUT_DIR/dashboard-token), set as localStorage.devSessionToken
#   RIG_SUMMARY  rig summary written by seed.py; "live" captions need "live": true there
#   VIDEO_OUT    output folder (default $OUT_DIR/video); compose.sh reads $VIDEO_OUT/manifest.json
#   FORBID_ON_SCREEN  optional comma-separated strings to add to the storyboard's list (host names, endpoints)
#   RECORD_SHOTS optional comma-separated shot ids to record (cards and frames are always rendered)
#   BOT_API_LOG  messages the rig's Bot API stand-in received (default $OUT_DIR/bot-api-messages.jsonl); the ask
#                shot shows the real delivered reply from it
#
# Text, timing and layout come from storyboard.json. The kept part of each shot is checked while it plays:
# any "forbid_on_screen" string (storyboard or env), or the token itself, in the page text fails the run.
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from frames import render_frames

here = Path(__file__).resolve().parent
board = json.loads((here / "storyboard.json").read_text())
OUT_DIR = os.environ.get("OUT_DIR", "")
app = os.environ.get("APP_URL", "http://127.0.0.1:5173").rstrip("/")
token = Path(os.environ.get("TOKEN_FILE") or f"{OUT_DIR}/dashboard-token").read_text().strip()
summary = json.loads(Path(os.environ.get("RIG_SUMMARY") or f"{OUT_DIR}/rig.json").read_text())
out = Path(os.environ.get("VIDEO_OUT") or f"{OUT_DIR}/video")
only = set(filter(None, os.environ.get("RECORD_SHOTS", "").split(",")))
forbid = board["forbid_on_screen"] + [x for x in os.environ.get("FORBID_ON_SCREEN", "").split(",") if x]
bot_log = Path(os.environ.get("BOT_API_LOG") or f"{OUT_DIR}/bot-api-messages.jsonl")
tabs = ["status", "sessions", "cron", "logs", "brain", "ask"]  # tab-bar order, matched by position

# A small touch ripple, since a recorded touch screen shows no pointer. Transform and opacity only.
ripple = """
(() => {
  let last = 0;
  const show = (x, y) => {
    const now = Date.now(); if (now - last < 80) return; last = now;
    const d = document.createElement('div');
    d.style.cssText = `position:fixed;left:${x - 22}px;top:${y - 22}px;width:44px;height:44px;border-radius:50%;` +
      'background:rgba(255,255,255,.35);border:2px solid rgba(255,255,255,.7);pointer-events:none;z-index:2147483647;' +
      'transform:scale(.4);opacity:1;transition:transform 450ms ease-out,opacity 450ms ease-out';
    document.documentElement.appendChild(d);
    requestAnimationFrame(() => { d.style.transform = 'scale(1.4)'; d.style.opacity = '0'; });
    setTimeout(() => d.remove(), 600);
  };
  addEventListener('touchstart', e => { const t = e.touches[0]; if (t) show(t.clientX, t.clientY); }, true);
  addEventListener('pointerdown', e => show(e.clientX, e.clientY), true);
})();
"""
problems: list[str] = []


class Shot:
    """One recorded clip: remembers which parts are kept (one or more ranges), the taps and sound cues inside
    them, and guards what is on screen once the first kept part starts."""

    def __init__(self, page, shot):
        self.page, self.shot, self.t0 = page, shot, time.monotonic()
        self.ranges: list[list] = []
        self.events: list[tuple[float, str]] = []

    @property
    def keep(self):
        return self.ranges[0][0] if self.ranges else None

    def now(self):
        return time.monotonic() - self.t0

    def mark(self, at=None):
        """Start a kept range (now, or at an earlier moment of the recording that is after the last range)."""
        self.ranges.append([self.now() if at is None else at, None])

    def cut(self):
        self.ranges[-1][1] = self.now()

    def cue(self, kind):
        self.events.append((self.now(), kind))

    def pause(self, sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            self.guard()
            self.page.wait_for_timeout(250)

    def guard(self):
        if self.keep is None:  # set-up before the kept part is cut away
            return
        texts = [f.evaluate("document.body ? document.body.innerText : ''") for f in self.page.frames]
        for text in texts:
            for bad in forbid + [token]:
                if bad in text:
                    line = next((x for x in text.splitlines() if bad in x), "")[:160]
                    shown = "the dashboard token" if bad == token else f"{bad!r} in {line!r}"
                    problems.append(f"{self.shot['id']}: {shown} is on screen")
                    raise SystemExit(f"stopped: {problems[-1]}")
        if self.page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
            problems.append(f"{self.shot['id']}: horizontal overflow")

    def tap(self, locator, after=0.9):
        locator.scroll_into_view_if_needed()
        self.pause(0.25)
        self.cue("tap")
        locator.tap()
        self.pause(after)

    def scroll(self, dy, after=1.0, target="window"):
        self.page.evaluate(f"({target}).scrollBy({{top: {dy}, behavior: 'smooth'}})")
        self.pause(after)

    def tab(self, key, after=1.2):
        self.tap(self.page.locator(".tab-bar button").nth(tabs.index(key)), after)

    def finish(self):
        if not self.ranges:
            self.mark()
        done = sum(e - s for s, e in self.ranges if e is not None)
        last = self.ranges[-1]
        if last[1] is None:
            target = max(self.shot["duration"] - done, 0)
            self.pause(max(last[0] + target + 0.4 - self.now(), 0))
            last[1] = last[0] + target

    def kept_events(self):
        """Taps and cues inside kept ranges, as seconds from the start of the shot in the video."""
        out, offset = [], 0.0
        for s, e in self.ranges:
            out += [[round(offset + t - s, 2), kind] for t, kind in self.events if s <= t < e]
            offset += e - s
        return out


def open_app(s):
    s.page.goto(f"{app}/", wait_until="networkidle")
    s.page.wait_for_selector(".tab-bar button")
    s.pause(1.0)


def shot_status(s):
    open_app(s)
    s.mark()
    s.pause(2.8)
    s.scroll(260, after=2.2)  # host and Hermes counts; the spend chart is left out (the rig's model is free, so it reads $0)
    s.scroll(-260, after=1.2)


def shot_cron(s):
    open_app(s)
    s.tab("cron")
    s.mark()
    s.pause(1.8)
    row = lambda name: s.page.locator(".cron-row", has_text=name)
    weekly = row("Weekly digest")
    s.tap(weekly.locator(".actions button").nth(0), after=1.4)   # Pause
    s.tap(weekly.locator(".actions button").nth(0), after=1.2)   # Resume
    morning = row("Morning ops brief")
    s.tap(morning.locator(".actions button").nth(1), after=1.4)  # Run now
    s.tap(morning.locator(".actions button").nth(2), after=1.6)  # Edit
    s.scroll(260, after=1.2)


def shot_sessions(s):
    open_app(s)
    s.tab("sessions")
    s.mark()
    s.pause(1.6)
    s.tap(s.page.locator(".list-item", has_text="release notes").first, after=1.8)
    s.scroll(500, after=2.0)
    s.scroll(500, after=1.5)


def shot_logs(s):
    open_app(s)
    s.tab("logs")
    rows = s.page.locator(".filter-bar .filter-row")
    # Set up before the kept part: gateway.log at the warning level. Agent/error logs and the unfiltered view carry host
    # paths and endpoint URLs, so the kept part stays on filtered gateway lines (the guard enforces it).
    rows.nth(0).locator("button").nth(2).tap()
    s.pause(1.5)
    rows.nth(1).locator("button").nth(2).tap()
    s.pause(2.0)
    s.mark()
    s.pause(2.5)
    s.tap(rows.nth(1).locator("button").nth(3), after=2.0)  # error level
    s.tap(s.page.locator(".section-title-row .ghost-btn"), after=1.5)


def shot_brain(s):
    open_app(s)
    s.scroll(5000, after=1.2)  # the language switch sits at the end of Status
    s.mark()
    s.pause(1.2)
    s.tap(s.page.locator(".lang-switch button").nth(1), after=1.4)  # EN -> BM
    s.tab("brain", after=0.2)
    box = s.page.locator(".filter-input")
    box.tap()
    box.press_sequentially(s.shot["filter"], delay=140)
    s.pause(2.0)
    s.scroll(220, after=1.5)


# Video-only overlays drawn over the recorded app: a small chip over the jump cut, and the reply Hermes delivered.
# Both are labelled for what they are; the app itself is never changed.
overlay = """
(() => {
  const css = document.createElement('style');
  css.textContent = `
  .vid-chip{position:fixed;left:50%;top:76px;transform:translateX(-50%);z-index:2147483646;padding:6px 14px;border-radius:999px;
    background:rgba(20,24,30,.92);color:#e8eef5;font:600 13px/1.3 -apple-system,system-ui,sans-serif;border:1px solid rgba(94,181,247,.5);
    opacity:0;transition:opacity 250ms;white-space:nowrap}
  .vid-chip.on{opacity:1}
  .vid-reply{position:fixed;left:12px;right:12px;bottom:96px;z-index:2147483646;border-radius:18px;padding:14px 16px 16px;
    background:#1b2733;color:#f2f5f9;box-shadow:0 18px 48px rgba(0,0,0,.55);border:1px solid rgba(94,181,247,.35);
    font:15px/1.4 -apple-system,system-ui,sans-serif;transform:translateY(24px);opacity:0;transition:transform 380ms ease-out,opacity 380ms}
  .vid-reply.on{transform:none;opacity:1}
  .vid-reply b{display:block;color:#5eb5f7;font-size:13px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:2px}
  .vid-reply small{display:block;color:#93a3b5;font-size:12px;margin-bottom:10px}
  .vid-reply p{margin:0;white-space:pre-wrap;max-height:46vh;overflow:hidden} .vid-reply strong{font-weight:700;color:#fff}`;
  document.head.appendChild(css);
  window.vidChip = (t) => { let c = document.querySelector('.vid-chip');
    if (!c) { c = document.createElement('div'); c.className = 'vid-chip'; document.body.appendChild(c); }
    c.textContent = t; requestAnimationFrame(() => c.classList.add('on')); };
  window.vidChipOff = () => { const c = document.querySelector('.vid-chip'); if (c) c.classList.remove('on'); };
  // Telegram MarkdownV2 as Telegram shows it: backslash-x = literal x, *bold*, _italic_. Built as DOM nodes, never as HTML.
  const mdv2 = (p, text) => { let bold = false, ital = false, buf = '';
    const flush = () => { if (!buf) return; const e = document.createElement(bold ? 'strong' : ital ? 'em' : 'span');
      e.textContent = buf; p.appendChild(e); buf = ''; };
    for (let i = 0; i < text.length; i++) { const c = text[i];
      if (c === '\\\\' && i + 1 < text.length) { buf += text[++i]; }
      else if (c === '*') { flush(); bold = !bold; } else if (c === '_') { flush(); ital = !ital; } else buf += c; }
    flush(); };
  window.vidReply = (title, note, text, mode) => { const d = document.createElement('div'); d.className = 'vid-reply';
    const b = document.createElement('b'); b.textContent = title; const n = document.createElement('small'); n.textContent = note;
    const p = document.createElement('p'); if (mode === 'MarkdownV2') mdv2(p, text); else p.textContent = text;
    d.append(b, n, p); document.body.appendChild(d);
    requestAnimationFrame(() => requestAnimationFrame(() => d.classList.add('on'))); };
})();
"""


def delivered_after(since):
    """The first message the Bot API stand-in received after `since` (epoch seconds), or None."""
    if not bot_log.exists():
        return None
    for line in bot_log.read_text(encoding="utf-8").splitlines():
        msg = json.loads(line)
        if msg["ts"] >= since and msg["method"] == "sendMessage":
            return msg
    return None


def shot_ask(s):
    """Ask in the panel, cut over the wait for Hermes's cron ticker, then show the reply Hermes delivered. The reply
    is the text Hermes actually sent to the rig's Bot API stand-in, shown in a labelled card (no mock chat screen)."""
    a = s.shot["ask"]
    open_app(s)
    s.page.evaluate(overlay)
    s.tab("ask")
    app_frame = s.page
    s.mark()
    s.pause(0.8)
    box = app_frame.locator(".compose textarea").first
    s.cue("tap")
    box.tap()
    box.press_sequentially(a["question"], delay=a["type_delay_ms"])
    s.pause(0.5)
    asked = time.time()
    s.tap(app_frame.locator(".compose .btn-primary").first, after=a["hold_queued_sec"])
    s.cut()
    state = app_frame.locator(".ask-status")
    deadline = time.monotonic() + a["max_wait_sec"]
    answering = None
    while not state.evaluate("e => e.classList.contains('delivered')"):
        if time.monotonic() > deadline or state.evaluate("e => e.classList.contains('failed')"):
            raise SystemExit(f"ask: no delivery in {a['max_wait_sec']} s ({state.inner_text()!r})")
        if answering is None and state.evaluate("e => e.classList.contains('running')"):
            answering = s.now()
            s.page.evaluate("t => window.vidChip(t)", a["skip_chip"])  # on screen for the whole kept part
        s.pause(0.25)
    delivered = s.now()
    msg = delivered_after(asked)
    for _ in range(60):  # the job can read as completed a moment before the send reaches the stand-in
        if msg is not None:
            break
        s.pause(0.25)
        msg = delivered_after(asked)
    if msg is None:
        raise SystemExit("ask: the job says delivered but the Bot API stand-in received no message")
    # The second part starts when Hermes picks the job up (at most lead_in_sec before delivery), chip already showing.
    start = max(answering if answering is not None else 0, delivered - a["lead_in_sec"])
    s.mark(at=max(start + 0.3, s.ranges[-1][1]))
    s.cue("chime")
    s.pause(a["hold_delivered_sec"])
    s.page.evaluate("() => window.vidChipOff()")
    s.page.evaluate("([t, n, x, m]) => window.vidReply(t, n, x, m)",
                    [a["delivered_title"], a["delivered_note"], msg["text"], msg.get("parse_mode", "")])
    s.cue("chime")
    s.pause(a["hold_reply_sec"])


actions = {"ask": shot_ask, "status": shot_status, "cron": shot_cron, "sessions": shot_sessions,
         "logs": shot_logs, "brain": shot_brain}


def record(p, browser, shot, raw: Path):
    scale = board["record"]["viewport_scale"]
    dev = p.devices["iPhone 13"]
    size = {"width": dev["viewport"]["width"] * scale, "height": dev["viewport"]["height"] * scale}
    raw.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(**dev, color_scheme=board["record"]["theme"], record_video_dir=str(raw),
                              record_video_size=size)
    ctx.add_init_script(f"localStorage.setItem('devSessionToken', {json.dumps(token)});"
                        f"localStorage.setItem('hermes-miniapp.lang', {json.dumps(board['record']['lang'])});")
    ctx.add_init_script(ripple)
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(app) else r.abort())
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    s = Shot(page, shot)
    actions[shot["id"]](s)
    s.finish()
    video = page.video
    ctx.close()
    problems.extend(f"{shot['id']}: page error: {e}" for e in errors)
    clip = raw / f"{shot['id']}.webm"
    Path(video.path()).replace(clip)
    ranges = [[round(a, 2), round(b, 2)] for a, b in s.ranges]
    print(f"recorded {shot['id']}: keep {ranges} for {shot['duration']}s")
    return {"clip": str(clip), "start": ranges[0][0], "ranges": ranges, "events": s.kept_events()}


def main():
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    old = {seg["id"]: seg for seg in json.loads(manifest_path.read_text())["segments"]} if manifest_path.exists() else {}
    with sync_playwright() as p:
        browser = p.webkit.launch()
        segments = render_frames(browser, board, summary, out / "frames")
        for seg in segments:
            shot = next(s for s in board["shots"] if s["id"] == seg["id"])
            if shot["kind"] == "card":
                continue
            if only and seg["id"] not in only and seg["id"] in old:
                seg.update({k: old[seg["id"]][k] for k in ("clip", "start", "ranges", "events") if k in old[seg["id"]]})
            else:
                seg.update(record(p, browser, shot, out / "raw"))
        browser.close()
    manifest_path.write_text(json.dumps({"canvas": board["canvas"], "phone": board["phone"], "fade_sec": board["fade_sec"],
                                         "audio": board["audio"], "segments": segments}, indent=2))
    print(f"manifest: {len(segments)} segments")
    if problems:
        print("problems:", *problems, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
