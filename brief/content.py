"""Ask Claude, with server-side web search, for today's content as strict JSON."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import anthropic
from pydantic import ValidationError

from . import config
from .schema import BriefContent
from .sun import SunTimes, act_labels
from .weather import DayWeather

SYSTEM_PROMPT = """You write a one-page morning brief, published before 6 AM Paris time on weekdays.

READER
Maurits, Chief of Staff, Accor Commercial, Digital & Tech. Lives in Saint-Cloud (Transilien L and U, A13), works in Issy-les-Moulineaux. Reads it on a phone over coffee.

VOICE
- English only. Concise and practical: what happens, when, and what it means for his day.
- Never use em dashes. Use commas, colons, semicolons or full stops instead.
- Paraphrase. No quotes longer than a few words.
- Times are Paris times written like 8 AM, 2:30 PM, 12 PM.
- Be specific: names, numbers, times, lines, stations. No filler, no hedging, no generic advice.

SOURCES
- Use the web search tool. Every item needs a real source URL that appeared in your search or fetch results, copied exactly. Never guess or construct a URL.
- Prefer the original article page, not a homepage, tag page or search page.
- If you cannot verify something, leave it out.
- Drop any section with nothing worth saying.

SECTIONS (the `sections` array; order does not matter, Python orders them)
1. coming_up: what is happening today that affects him. Paris and Ile-de-France strikes, works or disruptions (RATP, SNCF, Transilien L and U and Saint-Cloud station, A13 and boulevard peripherique closures, demonstrations, station closures); French public holidays or bank closures; Accor or hotel-industry events; major market or economic releases due today (with times). 0 to 4 items.
2. worth_knowing: 4 to 6 items from the last 24 to 48 hours. Accor, hotels and travel, OTAs, distribution, Amadeus and GDS, AI and big tech news that matters to commercial and digital teams, major France and Europe headlines. Never repeat a story from the previous pages (their URLs are listed in the request), even from a different outlet.
3. formula1: only when there is an F1 session (practice, qualifying, sprint or race) on the day the request names. One item giving the session and its Paris time. Otherwise leave it out.
4. next_week: only when the request says it is allowed. A short look ahead: 2 to 4 items for the coming week.

ITEM FORMAT
Each item has: title (short, plain, no trailing full stop), url, text (one or two sentences), link_phrase (three to eight words copied exactly from text; they become the link, so pick the words that name the source's claim).

TOP OF PAGE
- headline: one line that addresses Maurits by name and names EITHER what makes today distinct OR the shape of his day, never both. At most about 70 characters. No em dashes.
- acts: exactly three, in order: morning (from sunrise to noon), midday (noon to sunset), evening (from sunset). Each is one specific sentence that combines weather and what is happening in that window. The time ranges are drawn by the page; do not repeat them.
- marks: 0 to 3 real timed public events today that sit on the timeline, as [hour, short label]. Only real events with a known time between 7 AM and 11 PM (a march start, a station closure, a data release, an F1 session). Label: two to four words plus the time, for example "march, 2 PM". At most 22 characters. Leave the list empty rather than invent.
- weather_motif: pick from the data's suggestion unless your sources clearly show otherwise. rain means wet all day; showers means wet only for part of the day; clear means a dry, mostly sunny day.
- weather_line: one sentence for Saint-Cloud and Issy from the MET Norway data in the request: conditions through the day, min to max temperature, rain total if any, notable wind, and any official Meteo-France warning you find. No source name; the page adds the Yr link.

Return only the JSON object that matches the schema."""


def _norm(url: str) -> str:
    p = urlsplit(url.strip())
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path, p.query, ""))


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    searches: int = 0
    fetches: int = 0
    requests: int = 0

    def add(self, u) -> None:
        self.requests += 1
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0
        stu = getattr(u, "server_tool_use", None)
        if stu is not None:
            self.searches += getattr(stu, "web_search_requests", 0) or 0
            self.fetches += getattr(stu, "web_fetch_requests", 0) or 0

    @property
    def cost_usd(self) -> float:
        return round(
            self.input_tokens / 1e6 * config.PRICE_INPUT_PER_MTOK
            + self.output_tokens / 1e6 * config.PRICE_OUTPUT_PER_MTOK
            + self.cache_read / 1e6 * config.PRICE_CACHE_READ_PER_MTOK
            + self.cache_write / 1e6 * config.PRICE_CACHE_WRITE_PER_MTOK
            + self.searches * config.PRICE_PER_SEARCH,
            3,
        )


@dataclass
class ContentResult:
    content: BriefContent
    source_urls: set[str] = field(default_factory=set)
    usage: Usage = field(default_factory=Usage)


class ContentError(RuntimeError):
    def __init__(self, msg: str, usage: Usage | None = None):
        super().__init__(msg)
        self.usage = usage or Usage()


def build_request(day: date, st: SunTimes, weather: DayWeather | None, recent_urls: list[str],
                  feedback: list[str] | None = None) -> str:
    labels = act_labels(st)
    weekday = day.strftime("%A")
    lines = [
        f"Today is {weekday} {day.isoformat()} in Paris. The page is read around 6 to 8 AM.",
        f"Sunrise {st.sunrise:%H:%M}, sunset {st.sunset:%H:%M}.",
        f"The three acts cover: 1) {labels[0]}, 2) {labels[1]}, 3) {labels[2]}.",
        "",
        "WEATHER DATA (MET Norway Locationforecast, Saint-Cloud 48.844 N 2.219 E):",
        weather.as_prompt() if weather else "Unavailable today: keep weather_line short and say the forecast could not be loaded.",
        "",
    ]
    if weekday == "Friday":
        lines.append("Formula 1: today is Friday, and there is no weekend page. If there is an F1 weekend, the formula1 item may give today's session and the weekend's qualifying and race in Paris time.")
    if weekday == "Saturday":
        lines.append("Saturday: next_week IS allowed and replaces formula1. Give the week ahead.")
    else:
        lines.append("next_week is NOT allowed today.")
    lines += ["", "URLs already used on recent pages (do not repeat these stories):"]
    lines += [f"- {u}" for u in recent_urls[-120:]] or ["- none"]
    if feedback:
        lines += ["", "A previous attempt was rejected for these reasons. Fix every one:"]
        lines += [f"- {f}" for f in feedback]
    lines += ["", "Search now, then return the JSON."]
    return "\n".join(lines)


def _collect_sources(blocks, into: set[str]) -> None:
    for b in blocks:
        t = getattr(b, "type", "")
        c = getattr(b, "content", None)
        if t == "web_search_tool_result" and isinstance(c, list):
            for r in c:
                if getattr(r, "url", None):
                    into.add(_norm(r.url))
        elif t == "web_fetch_tool_result" and c is not None and getattr(c, "url", None):
            into.add(_norm(c.url))
        elif t == "server_tool_use" and getattr(b, "name", "") == "web_fetch":
            u = (getattr(b, "input", None) or {}).get("url")
            if u:
                into.add(_norm(u))


def _json_text(blocks) -> str:
    texts = [b.text for b in blocks if getattr(b, "type", "") == "text"]
    if not texts:
        raise ContentError("model returned no text block")
    raw = texts[-1].strip()
    if not raw.startswith("{"):
        m = re.search(r"\{.*\}", raw, re.S)
        raw = m.group(0) if m else raw
    return raw


def generate(day: date, st: SunTimes, weather: DayWeather | None, recent_urls: list[str],
             feedback: list[str] | None = None, client: anthropic.Anthropic | None = None,
             blocked_domains: list[str] | None = None) -> ContentResult:
    client = client or anthropic.Anthropic(max_retries=3, timeout=900)
    usage = Usage()
    sources: set[str] = set()
    messages: list[dict] = [{"role": "user", "content": build_request(day, st, weather, recent_urls, feedback)}]
    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": config.MAX_SEARCHES,
            "user_location": {"type": "approximate", "city": "Saint-Cloud", "region": "Ile-de-France",
                              "country": "FR", "timezone": "Europe/Paris"},
        },
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8, "max_content_tokens": 8000},
    ]
    if blocked_domains:
        # Sites whose pages failed the link check behind bot walls on earlier runs.
        for t in tools:
            t["blocked_domains"] = blocked_domains
    final = None
    for _ in range(6):  # pause_turn continuations
        with client.beta.messages.stream(
            model=config.MODEL,
            max_tokens=64000,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
            output_config={
                "effort": config.EFFORT,
                "format": {"type": "json_schema", "schema": anthropic.transform_schema(BriefContent)},
            },
            cache_control={"type": "ephemeral"},
            fallbacks="default",
            betas=["server-side-fallback-2026-07-01"],
        ) as stream:
            final = stream.get_final_message()
        usage.add(final.usage)
        _collect_sources(final.content, sources)
        if final.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": final.content})
            continue
        break
    if final is None or final.stop_reason in ("pause_turn", "refusal", "max_tokens"):
        raise ContentError(f"model stopped with {getattr(final, 'stop_reason', None)}", usage)
    raw = _json_text(final.content)
    try:
        content = BriefContent.model_validate_json(raw)
    except ValidationError as e:
        problems = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
        raise ContentError("schema: " + "; ".join(problems), usage) from e
    except json.JSONDecodeError as e:
        raise ContentError(f"invalid JSON: {e}", usage) from e
    return ContentResult(content=content, source_urls=sources, usage=usage)


def unsourced(content: BriefContent, sources: set[str]) -> list[str]:
    """URLs in the content that never appeared in a search or fetch result."""
    if not sources:
        return []
    return [u for u in content.urls() if _norm(u) not in sources]
