# Record the demo video's screen clips against a running rig, and render its cards and frames.
#
#   uv run --with playwright==1.58.0 --with pillow python scripts/video/record.py
#
# Environment:
#   APP_URL      the Vite dev server (default http://127.0.0.1:5173); its /api proxy points at the rig
#   TOKEN_FILE   the rig's dashboard token (default $OUT_DIR/dashboard-token), set as localStorage.devSessionToken
#   RIG_SUMMARY  rig summary written by seed.py; "live" captions need "live": true there
#   VIDEO_OUT    output folder (default $OUT_DIR/video); compose.sh reads $VIDEO_OUT/manifest.json
#   RECORD_SHOTS optional comma-separated shot ids to record (cards and frames are always rendered)
#
# Text, timing and layout come from storyboard.json. The kept part of each shot is checked while it plays:
# any storyboard "forbid_on_screen" string, or the token itself, in the page text fails the run.
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
tabs = ["status", "sessions", "cron", "logs", "brain", "send"]  # tab-bar order, matched by position

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
    """One recorded clip: remembers when the kept part starts and guards what is on screen."""

    def __init__(self, page, shot):
        self.page, self.shot, self.t0, self.keep = page, shot, time.monotonic(), None

    def mark(self):
        self.keep = time.monotonic() - self.t0

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
            for bad in board["forbid_on_screen"] + [token]:
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
        locator.tap()
        self.pause(after)

    def scroll(self, dy, after=1.0, target="window"):
        self.page.evaluate(f"({target}).scrollBy({{top: {dy}, behavior: 'smooth'}})")
        self.pause(after)

    def tab(self, key, after=1.2):
        self.tap(self.page.locator(".tab-bar button").nth(tabs.index(key)), after)

    def finish(self):
        if self.keep is None:
            self.mark()
        left = self.keep + self.shot["duration"] + 0.4 - (time.monotonic() - self.t0)
        self.pause(max(left, 0))


def open_app(s):
    s.page.goto(f"{app}/", wait_until="networkidle")
    s.page.wait_for_selector(".tab-bar button")
    s.pause(1.0)


def shot_open(s):
    mock = dict(s.shot["mock"], app_url=f"{app}/")
    html = (here / "telegram-mock.html").read_text().replace(
        "<script>", f"<script>window.MOCK = {json.dumps(mock)};</script>\n<script>", 1)
    s.page.route(f"{app}/__mock__", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
    s.page.goto(f"{app}/__mock__", wait_until="load")
    s.pause(0.3)
    s.mark()
    s.pause(2.2)
    s.tap(s.page.locator("#menu"), after=0)
    s.page.frame_locator("iframe").locator(".tab-bar button").first.wait_for()


def shot_status(s):
    open_app(s)
    s.mark()
    s.pause(2.5)
    s.scroll(420, after=1.6)
    s.tap(s.page.locator(".filter-pill").nth(1), after=2.2)
    s.scroll(-420, after=1.0)


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


actions = {"open": shot_open, "status": shot_status, "cron": shot_cron, "sessions": shot_sessions,
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
    print(f"recorded {shot['id']}: keep from {s.keep:.2f}s for {shot['duration']}s")
    return {"clip": str(clip), "start": round(s.keep, 2)}


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
                seg.update({k: old[seg["id"]][k] for k in ("clip", "start")})
            else:
                seg.update(record(p, browser, shot, out / "raw"))
        browser.close()
    manifest_path.write_text(json.dumps({"canvas": board["canvas"], "phone": board["phone"],
                                         "fade_sec": board["fade_sec"], "segments": segments}, indent=2))
    print(f"manifest: {len(segments)} segments")
    if problems:
        print("problems:", *problems, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
