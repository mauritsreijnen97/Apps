"""Quality gates. The build only publishes a page that passes all of them."""
from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .schema import EM_DASH

# Many news sites refuse obvious bots, so the link check looks like a browser.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


@dataclass
class GateReport:
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    dead: list[str] = field(default_factory=list)
    walled: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def extend(self, other: "GateReport") -> None:
        self.failures += other.failures
        self.notes += other.notes
        self.screenshots += other.screenshots
        self.dead += other.dead
        self.walled += other.walled


# 1. Typography ---------------------------------------------------------------

def check_em_dash(html: str) -> GateReport:
    r = GateReport()
    n = html.count(EM_DASH)
    if n:
        i = html.index(EM_DASH)
        snippet = re.sub(r"\s+", " ", html[max(0, i - 40): i + 40])
        r.failures.append(f"em dash (U+2014) found {n} time(s), first near: ...{snippet}...")
    return r


# 2. Links --------------------------------------------------------------------

_WALLS = re.compile(r"cloudflare|captcha|access denied|akamai|datadome|perimeterx|just a moment", re.I)


def url_status(url: str, session: requests.Session | None = None, timeout: float = 15) -> tuple[bool, str]:
    """HEAD, falling back to GET. 2xx and 3xx pass. A 401/403/429 behind a bot
    wall is reported as such: still a failure, but the host gets remembered."""
    http = session or requests
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "en,fr;q=0.8"}
    last = "no response"
    for method in ("HEAD", "GET"):
        try:
            resp = http.request(method, url, headers=headers, timeout=timeout, allow_redirects=True, stream=method == "HEAD")
            code = resp.status_code
            if 200 <= code < 400:
                resp.close()
                return True, f"{method} {code}"
            last = f"{method} {code}"
            if method == "GET" and code in (401, 403, 429) and _WALLS.search(resp.text[:20000] + str(resp.headers)):
                last += " bot-wall"
            resp.close()
        except requests.RequestException as e:
            last = f"{method} {type(e).__name__}"
    return False, last


def check_urls(urls: list[str], session: requests.Session | None = None) -> GateReport:
    r = GateReport()
    unique = list(dict.fromkeys(urls))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda u: (u, *url_status(u, session)), unique))
    for url, ok, why in results:
        (r.notes if ok else r.failures).append(f"{'ok' if ok else 'dead link'} [{why}] {url}")
        if not ok:
            r.dead.append(url)
            if "bot-wall" in why:
                r.walled.append(url)
    return r


# 3. Rendering ----------------------------------------------------------------

_PROBE = """() => {
  const doc = document.documentElement;
  const h1 = document.querySelector('h1');
  const lh = parseFloat(getComputedStyle(h1).lineHeight);
  const boxes = [...document.querySelectorAll('#marks text')].map(t => {
    const b = t.getBoundingClientRect(); return {x:b.x, y:b.y, w:b.width, h:b.height, text:t.textContent};
  });
  const overlaps = [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) overlaps.push([a.text, b.text]);
  }
  return {
    scrollW: doc.scrollWidth, clientW: doc.clientWidth,
    headlineLines: Math.round(h1.getBoundingClientRect().height / lh),
    marks: boxes.length, overlaps,
  };
}"""


def _launch(p):
    exe = os.environ.get("BRIEF_CHROMIUM")
    if exe:
        return p.chromium.launch(executable_path=exe)
    try:
        return p.chromium.launch()
    except Exception:
        fallback = "/opt/pw-browsers/chromium"  # preinstalled in some sandboxes
        if Path(fallback).exists():
            return p.chromium.launch(executable_path=fallback)
        raise


def check_render(html_path: Path, shots_dir: Path | None, *, wait_ms: int = 4000, expected_marks: int | None = None) -> GateReport:
    from playwright.sync_api import sync_playwright

    r = GateReport()
    if shots_dir:
        shots_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            for width in (960, 390):
                page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(html_path.resolve().as_uri())
                page.wait_for_timeout(wait_ms)
                m = page.evaluate(_PROBE)
                if m["scrollW"] > m["clientW"]:
                    r.failures.append(f"{width}px: horizontal scroll ({m['scrollW']} > {m['clientW']})")
                for a, b in m["overlaps"]:
                    r.failures.append(f"{width}px: mark labels overlap: {a!r} and {b!r}")
                if width == 390 and m["headlineLines"] > 3:
                    r.failures.append(f"390px: headline takes {m['headlineLines']} lines (max 3)")
                if expected_marks is not None and m["marks"] != expected_marks:
                    r.failures.append(f"{width}px: {m['marks']} mark labels drawn, expected {expected_marks}")
                for e in errors:
                    r.failures.append(f"{width}px: script error: {e}")
                r.notes.append(f"{width}px: headline {m['headlineLines']} line(s), {m['marks']} mark(s)")
                if shots_dir:
                    page.wait_for_timeout(600)  # let the last fade settle before the picture
                    shot = shots_dir / f"brief-{width}.png"
                    page.screenshot(path=str(shot), full_page=True)
                    r.screenshots.append(str(shot))
                page.close()
        finally:
            browser.close()
    return r


def run_all(html_path: Path, urls: list[str], shots_dir: Path | None, *, check_links: bool = True,
            expected_marks: int | None = None) -> GateReport:
    wait_ms = int(os.environ.get("BRIEF_RENDER_WAIT_MS", "4000"))
    html = html_path.read_text(encoding="utf-8")
    report = check_em_dash(html)
    if check_links:
        report.extend(check_urls(urls))
    report.extend(check_render(html_path, shots_dir, wait_ms=wait_ms, expected_marks=expected_marks))
    return report


def links_in(html: str) -> list[str]:
    return re.findall(r'href="(https?://[^"]+)"', html)


if __name__ == "__main__":  # python -m brief.gates dist/index.html
    from html import unescape

    from .config import SCREENSHOTS

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/index.html")
    text = target.read_text(encoding="utf-8")
    rep = run_all(target, [unescape(u) for u in links_in(text)], SCREENSHOTS,
                  check_links="--no-links" not in sys.argv)
    for line in rep.notes:
        print("  " + line)
    for line in rep.failures:
        print("FAIL " + line)
    print("gates passed" if rep.ok else f"{len(rep.failures)} gate failure(s)")
    sys.exit(0 if rep.ok else 1)
