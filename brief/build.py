"""Entry point: python -m brief.build -> dist/index.html

Exit codes: 0 fresh page published or already built today, 3 yesterday's page
republished with a "not updated today" note, 1 nothing could be published.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from . import config, gates
from .content import ContentError, ContentResult, Usage, _norm, generate, unsourced
from .history import History
from pydantic import ValidationError
from .config import YR_URL
from .render import render
from .schema import BriefContent, SectionKind
from .sun import sun_times
from .weather import DayWeather, fetch_forecast, load_fixture, summarise

STALE_NOTE = "not updated today"


def log(msg: str) -> None:
    print(f"[brief {datetime.now(config.TZ):%H:%M:%S}] {msg}", flush=True)


def page_meta(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    head = path.read_text(encoding="utf-8")[:40000]
    return dict(re.findall(r'<meta name="brief-(date|status)" content="([^"]*)">', head))


def already_built(dist: Path, day: date) -> bool:
    m = page_meta(dist / "index.html")
    return m.get("date") == day.isoformat() and m.get("status") == "fresh"


def tidy(content: BriefContent, recent: list[str], sources: set[str],
         dead: list[str] | None = None) -> tuple[BriefContent, list[str]]:
    """Drop repeated, unsourced or unreachable items. Returns the content and what was dropped.

    Raises a ValidationError when the trim leaves a section too thin (for example
    fewer than four worth_knowing items), which sends the build into its retry.
    """
    seen = {_norm(u) for u in recent}
    unsrc = {_norm(u) for u in unsourced(content, sources)}
    gone = {_norm(u) for u in dead or []}
    dropped: list[str] = []
    sections = []
    for s in content.sections:
        keep = []
        for i in s.items:
            n = _norm(i.url)
            if s.kind == SectionKind.worth_knowing and n in seen:
                dropped.append(f"repeat from a recent page: {i.url}")
            elif n in unsrc:
                dropped.append(f"URL not found in search results: {i.url}")
            elif n in gone:
                dropped.append(f"link failed the check: {i.url}")
            else:
                keep.append(i)
        if keep:
            sections.append(s.model_copy(update={"items": keep}))
    data = content.model_dump()
    data["sections"] = [s.model_dump() for s in sections]
    # Re-validate so worth_knowing still holds 4 to 6 items after the trim.
    return BriefContent.model_validate(data), dropped


def make_stale(previous_html: str) -> str:
    html = previous_html.replace('<meta name="brief-status" content="fresh">', '<meta name="brief-status" content="stale">')
    if STALE_NOTE in html:
        return html
    note = f' · <span style="color:var(--grey)">{STALE_NOTE}</span>'
    return re.sub(r'(<p class="date rise d1">)(.*?)(</p>)', lambda m: m.group(1) + m.group(2) + note + m.group(3), html, count=1)


class BlockedHosts:
    """Hosts whose pages sit behind bot walls. Web search skips them next time."""

    KEEP_DAYS = 60

    def __init__(self, path: Path):
        self.path = path
        self.hosts: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def add(self, urls: list[str], day: date) -> None:
        for u in urls:
            host = urlsplit(u).netloc.lower().removeprefix("www.")
            if host:
                self.hosts[host] = day.isoformat()

    def domains(self, day: date) -> list[str]:
        cutoff = date.fromordinal(day.toordinal() - self.KEEP_DAYS).isoformat()
        fresh = sorted((d, h) for h, d in self.hosts.items() if d >= cutoff)
        return [h for _, h in fresh][-50:]

    def save(self) -> None:
        self.path.write_text(json.dumps(self.hosts, indent=1, sort_keys=True) + "\n")


def get_weather(day: date, st, fixture: Path | None) -> DayWeather | None:
    for attempt in range(3):
        try:
            data = load_fixture(fixture) if fixture else fetch_forecast()
            return summarise(data, day, st)
        except Exception as e:  # weather must never stop the page
            log(f"weather attempt {attempt + 1} failed: {e}")
            time.sleep(3 * (attempt + 1))
    return None


def set_output(**kv: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m brief.build")
    ap.add_argument("--date", type=date.fromisoformat, help="Paris date to build (default: today)")
    ap.add_argument("--force", action="store_true", help="rebuild even if today's page exists")
    ap.add_argument("--content", type=Path, help="use this JSON instead of calling Claude")
    ap.add_argument("--weather-json", type=Path, help="use a saved MET Norway response")
    ap.add_argument("--no-link-check", action="store_true", help="skip the URL gate (offline development only)")
    ap.add_argument("--attempts", type=int, default=2)
    args = ap.parse_args(argv)

    dist, shots = config.DIST, config.SCREENSHOTS
    day = args.date or datetime.now(config.TZ).date()
    index = dist / "index.html"
    if already_built(dist, day) and not args.force:
        log(f"today's page ({day}) is already built; nothing to do")
        set_output(status="skipped")
        return 0

    dist.mkdir(parents=True, exist_ok=True)
    st = sun_times(day)
    log(f"building {day}: sunrise {st.sunrise:%H:%M}, sunset {st.sunset:%H:%M}")
    weather = get_weather(day, st, args.weather_json)
    log("weather: " + (weather.as_prompt().replace("\n", " | ") if weather else "unavailable"))
    history = History(dist / "history.json")
    blocked = BlockedHosts(dist / "blocked-hosts.json")
    recent = history.recent(day)

    record: dict = {"date": day.isoformat(), "model": config.MODEL, "attempts": [], "started": datetime.now(config.TZ).isoformat()}
    total = Usage()
    feedback: list[str] | None = None
    candidate = dist / ".candidate.html"

    for n in range(1, args.attempts + 1):
        attempt: dict = {"n": n}
        try:
            if args.content:
                result = ContentResult(BriefContent.model_validate_json(args.content.read_text()))
            else:
                log(f"attempt {n}: asking {config.MODEL} with web search")
                result = generate(day, st, weather, recent, feedback, blocked_domains=blocked.domains(day))
            u = result.usage
            for k in ("input_tokens", "output_tokens", "cache_read", "cache_write", "searches", "fetches", "requests"):
                setattr(total, k, getattr(total, k) + getattr(u, k))
            attempt["usage"] = {**u.__dict__, "cost_usd": u.cost_usd}
            content, dropped = tidy(result.content, recent, result.source_urls)
            # Links first: an unreachable source drops its item rather than the page.
            if not args.no_link_check:
                links = gates.check_urls([*content.urls(), YR_URL])
                for line in links.notes:
                    log("  " + line)
                blocked.add(links.walled, day)
                blocked.save()
                if YR_URL in links.dead:
                    log("Yr link failed its check; dropping the Yr link is not an option, so this attempt fails")
                    raise RuntimeError(f"weather source link failed: {YR_URL}")
                if links.dead:
                    attempt["dead"] = links.dead
                    for line in links.failures:
                        log("  " + line)
                    content, more = tidy(content, [], set(), dead=links.dead)
                    dropped += more
            attempt["dropped"] = dropped
            for d in dropped:
                log("dropped " + d)
            page = render(day, content, st, weather)
            candidate.write_text(page.html, encoding="utf-8")
            report = gates.check_em_dash(page.html)
            report.extend(gates.check_render(candidate, shots, wait_ms=int(os.environ.get("BRIEF_RENDER_WAIT_MS", "4000")),
                                             expected_marks=len(content.marks)))
            attempt["gates"] = {"failures": report.failures, "notes": report.notes}
            for line in report.notes:
                log("  " + line)
            if not report.ok:
                for line in report.failures:
                    log("GATE FAIL " + line)
                feedback = report.failures
                record["attempts"].append(attempt)
                continue
        except ContentError as e:
            log(f"attempt {n}: content failed: {e}")
            attempt["error"] = str(e)
            u = e.usage
            for k in ("input_tokens", "output_tokens", "cache_read", "cache_write", "searches", "fetches", "requests"):
                setattr(total, k, getattr(total, k) + getattr(u, k))
            feedback = [str(e)]
            record["attempts"].append(attempt)
            continue
        except ValidationError as e:  # the trim left a section too thin
            msg = "after dropping repeated, unsourced or unreachable items: " + "; ".join(x["msg"] for x in e.errors())
            log(f"attempt {n}: {msg}")
            attempt["error"] = msg
            feedback = [msg, *[f"this source failed the link check, use a different site for the same fact: {u}"
                               for u in attempt.get("dead", [])]]
            record["attempts"].append(attempt)
            continue
        except Exception as e:  # API outage, browser crash...
            log(f"attempt {n}: failed: {type(e).__name__}: {e}")
            attempt["error"] = f"{type(e).__name__}: {e}"
            feedback = [f"{type(e).__name__}: {e}"]
            record["attempts"].append(attempt)
            continue

        # Passed every gate: publish.
        record["attempts"].append(attempt)
        candidate.replace(index)
        (dist / "archive").mkdir(exist_ok=True)
        shutil.copyfile(index, dist / "archive" / f"{day.isoformat()}.html")
        (dist / "archive" / f"{day.isoformat()}.json").write_text(content.model_dump_json(indent=1) + "\n")
        history.record(day, content.urls())
        history.save()
        record.update(status="fresh", usage={**total.__dict__, "cost_usd": total.cost_usd},
                      weather=weather.to_json() if weather else None, finished=datetime.now(config.TZ).isoformat())
        (dist / "build.json").write_text(json.dumps(record, indent=1, default=str) + "\n")
        spent = f"model cost about ${total.cost_usd:.2f}" if total.requests else "no model call"
        log(f"published {index} ({spent})")
        set_output(status="fresh")
        return 0

    candidate.unlink(missing_ok=True)
    record.update(usage={**total.__dict__, "cost_usd": total.cost_usd}, finished=datetime.now(config.TZ).isoformat())
    if index.exists():
        index.write_text(make_stale(index.read_text(encoding="utf-8")), encoding="utf-8")
        record["status"] = "stale"
        (dist / "build.json").write_text(json.dumps(record, indent=1, default=str) + "\n")
        log("all attempts failed; republished the previous page with a 'not updated today' note")
        set_output(status="stale")
        return 3
    record["status"] = "failed"
    (dist / "build.json").write_text(json.dumps(record, indent=1, default=str) + "\n")
    log("all attempts failed and there is no previous page to fall back on")
    set_output(status="failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
