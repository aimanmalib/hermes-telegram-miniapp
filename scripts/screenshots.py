# Capture README screenshots from the demo build (WebKit, iPhone 13).
#   cd web && npm run build:demo && python3 -m http.server 3392 --bind 127.0.0.1 --directory ../dist-demo
#   uv run --with playwright==1.58.0 --with pillow python scripts/screenshots.py http://127.0.0.1:3392 docs/screenshots
# Requests to anything other than the local server are blocked and reported.
import sys, io
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image

BASE = sys.argv[1]
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
TABS = [("status", "Status"), ("sessions", "Sessions"), ("cron", "Cron"),
        ("logs", "Logs"), ("brain", "Brain"), ("send", "Send")]
external = []


def save(png, name):
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img = img.resize((585, round(img.height * 585 / img.width)), Image.LANCZOS)
    img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    dest = OUT / name
    img.save(dest, optimize=True)
    print(dest.name, dest.stat().st_size)

with sync_playwright() as p:
    b = p.webkit.launch()
    for theme in ("light", "dark"):
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
        page.goto(f"{BASE}/?theme={theme}", wait_until="networkidle")
        page.wait_for_timeout(600)
        for key, label in TABS:
            if only and key not in only:
                continue
            page.locator(".tab-bar button", has_text=label).click()
            page.wait_for_timeout(700)
            save(page.screenshot(), f"{key}-{theme}.png")
        if not only or "usage" in only:
            page.locator(".tab-bar button", has_text="Status").click()
            page.wait_for_timeout(700)
            page.evaluate("document.querySelector('.section-title-row').scrollIntoView({block: 'start'}); window.scrollBy(0, -110)")
            page.wait_for_timeout(500)
            save(page.screenshot(), f"usage-{theme}.png")
        if errors:
            print("ERRORS", theme, errors)
        ctx.close()
    b.close()
print("blocked external requests:", sorted(set(external)))
