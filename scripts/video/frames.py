"""Render the video's still layers with the browser: title/security/closing cards, and for each screen shot
a background (caption) and a foreground (generic phone bezel with a transparent screen).

compose.sh stacks background → scaled clip → foreground, so the bezel's rounded inner edge trims the clip.
All text comes from storyboard.json.
"""
import html
from pathlib import Path

font = '-apple-system, "Segoe UI", Roboto, "Liberation Sans", Arial, sans-serif'
BASE_CSS = f"""
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ width: 100%; height: 100%; font-family: {font}; color: #f2f5f9; }}
.bg {{ position: absolute; inset: 0; background: radial-gradient(120% 70% at 50% 0%, #22324a 0%, #0f1622 55%, #0a0f17 100%); }}
"""
check = ('<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#5eb5f7" stroke-width="2.4" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5l10 -10"/></svg>')


def phone_box(board):
    """Screen and bezel rectangles on the canvas, from the storyboard's phone settings."""
    cw, ch = board["canvas"]["width"], board["canvas"]["height"]
    ph = board["phone"]
    sw = ph["screen_width"]
    sh = round(sw * 844 / 390 / 2) * 2  # iPhone 13 viewport ratio, even for H.264
    b = ph["bezel"]
    ow, oh = sw + 2 * b, sh + 2 * b
    ox, oy = (cw - ow) // 2, ch - ph["bottom_margin"] - oh
    return {"x": ox + b, "y": oy + b, "w": sw, "h": sh}, {"x": ox, "y": oy, "w": ow, "h": oh}


def caption_text(shot, summary):
    text = shot["caption"]
    if shot.get("needs_live") and summary.get("live") is not True:
        raise SystemExit(f"{shot['id']}: caption claims a live Hermes but the rig summary is not live")
    return text.format(hermes_version=summary.get("hermes_version", "?"))


def card_html(shot, board):
    lines = [html.escape(x) for x in shot["lines"]]
    if shot["id"] == "title":
        body = (f'<div class="kicker">Hermes Agent plugin</div><h1>{lines[0]}</h1><p class="sub">{lines[1]}</p>')
    elif shot["id"] == "security":
        items = "".join(f"<li>{check}<span>{x}</span></li>" for x in lines[1:])
        body = f"<h2>{lines[0]}</h2><ul>{items}</ul>"
    else:
        rest = "".join(f'<p class="sub">{x}</p>' for x in lines[1:])
        body = f'<h2 class="repo">{lines[0]}</h2>{rest}'
    return f"""<style>{BASE_CSS}
.card {{ position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; padding: 0 90px; gap: 36px; }}
.kicker {{ font-size: 40px; letter-spacing: .14em; text-transform: uppercase; color: #5eb5f7; font-weight: 700; }}
h1 {{ font-size: 112px; line-height: 1.04; font-weight: 800; letter-spacing: -.02em; }}
h2 {{ font-size: 72px; line-height: 1.1; font-weight: 800; }}
h2.repo {{ font-size: 50px; color: #5eb5f7; word-break: break-all; }}
.sub {{ font-size: 54px; line-height: 1.25; color: #c3cfdd; }}
ul {{ list-style: none; padding: 0; display: flex; flex-direction: column; gap: 34px; }}
li {{ display: flex; gap: 24px; align-items: flex-start; font-size: 50px; line-height: 1.2; }}
li svg {{ flex: none; margin-top: 6px; }}
li span {{ min-width: 0; overflow-wrap: anywhere; }}
</style><div class="bg"></div><div class="card">{body}</div>"""


def back_html(caption, box):
    return f"""<style>{BASE_CSS}
.cap {{ position: absolute; left: 60px; right: 60px; top: 0; height: {box['y'] - 20}px; display: flex; align-items: center;
  justify-content: center; text-align: center; font-size: 54px; line-height: 1.18; font-weight: 700; }}
.screen {{ position: absolute; left: {box['x']}px; top: {box['y']}px; width: {box['w']}px; height: {box['h']}px; background: #000; }}
</style><div class="bg"></div><div class="cap">{html.escape(caption)}</div><div class="screen"></div>"""


def front_html(outer, board):
    ph = board["phone"]
    return f"""<style>* {{ margin: 0; }} html, body {{ background: transparent; }}
.bezel {{ position: absolute; left: {outer['x']}px; top: {outer['y']}px; width: {outer['w']}px; height: {outer['h']}px;
  border: {ph['bezel']}px solid #15181e; border-radius: {ph['radius']}px; box-sizing: border-box;
  box-shadow: 0 0 0 2px #3a4150, 0 30px 80px rgba(0, 0, 0, .55); }}
</style><div class="bezel"></div>"""


def render_frames(browser, board, summary, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    cw, ch = board["canvas"]["width"], board["canvas"]["height"]
    page = browser.new_page(viewport={"width": cw, "height": ch}, device_scale_factor=1)
    screen, outer = phone_box(board)

    def shoot(markup, name, transparent=False):
        page.set_content(f"<!doctype html><html><body>{markup}</body></html>")
        page.wait_for_timeout(150)
        path = out / name
        page.screenshot(path=str(path), omit_background=transparent)
        return str(path)

    front = shoot(front_html(outer, board), "front.png", transparent=True)
    segments = []
    for shot in board["shots"]:
        seg = {"id": shot["id"], "kind": shot["kind"], "duration": shot["duration"]}
        if shot["kind"] == "card":
            seg["png"] = shoot(card_html(shot, board), f"{shot['id']}-card.png")
            seg["subtitle"] = " · ".join(shot["lines"])
        else:
            caption = caption_text(shot, summary)
            seg.update(back=shoot(back_html(caption, screen), f"{shot['id']}-back.png"), front=front, screen=screen,
                       subtitle=caption)
        segments.append(seg)
    page.close()
    return segments
