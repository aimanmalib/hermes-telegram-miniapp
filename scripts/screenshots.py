# Capture README screenshots from the demo build (WebKit, iPhone 13).
#   cd web && npm run build:demo && python3 -m http.server 3392 --bind 127.0.0.1 --directory ../dist-demo
#   uv run --with playwright==1.58.0 --with pillow python scripts/screenshots.py http://127.0.0.1:3392 docs/screenshots
# Optional third argument: comma-separated names to capture (e.g. "cron,usage").
# Requests to anything other than the local server are blocked and reported.
# Exits non-zero on page errors or horizontal overflow.
import sys, io
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = sys.argv[1]
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
# Tabs in tab-bar order. Buttons are clicked by position, so the labels may be in any language.
TABS = ["status", "sessions", "cron", "logs", "brain", "send"]
# (theme, lang, tabs to capture, file suffix). The Malay pass shows one tab to document the translation.
PASSES = [("light", "en", TABS + ["usage"], ""), ("dark", "en", TABS + ["usage"], ""),
          ("light", "ms", ["cron"], "-ms")]
external, problems = [], []


def save(png, name):
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img = img.resize((585, round(img.height * 585 / img.width)), Image.LANCZOS)
    img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    dest = OUT / name
    img.save(dest, optimize=True)
    print(dest.name, dest.stat().st_size)


def open_tab(page, key):
    page.locator(".tab-bar button").nth(TABS.index(key)).click()
    page.wait_for_timeout(700)
    if page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
        problems.append(f"horizontal overflow on {key}")


with sync_playwright() as p:
    b = p.webkit.launch()
    for theme, lang, shots, suffix in PASSES:
        wanted = [s for s in shots if not only or s in only]
        if not wanted:
            continue
        ctx = b.new_context(**p.devices["iPhone 13"], color_scheme=theme)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        def route(r):
            if r.request.url.startswith(BASE):
                return r.continue_()
            external.append(r.request.url)
            return r.abort()
        page.route("**/*", route)
        page.goto(f"{BASE}/?theme={theme}&lang={lang}", wait_until="networkidle")
        page.wait_for_timeout(600)
        for key in wanted:
            if key == "usage":
                open_tab(page, "status")
                page.evaluate("document.querySelector('.section-title-row').scrollIntoView({block: 'start'}); window.scrollBy(0, -110)")
                page.wait_for_timeout(500)
            else:
                open_tab(page, key)
            save(page.screenshot(), f"{key}{suffix}-{theme}.png")
        problems += [f"{theme}/{lang}: {e}" for e in errors]
        ctx.close()
    b.close()
print("blocked external requests:", sorted(set(external)))
if problems:
    print("PROBLEMS", *problems, sep="\n  ")
    sys.exit(1)
