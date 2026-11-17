"""BriefContent + sun + weather -> HTML, through the Jinja template."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .config import TEMPLATES, YR_URL
from .schema import SECTION_ORDER, SECTION_TITLES, BriefContent, WeatherMotif
from .sun import SunTimes, act_labels
from .weather import DayWeather

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html", "j2"]),
    keep_trailing_newline=True,
)

# Where each part of the day sits in the scene (reference positions).
_CLOUD_AT = {"morning": "translate(-95 -6)", "midday": "translate(220 0)"}
_BIRDS_AT = {"morning": "translate(0 0)", "midday": "translate(330 0)"}
_SUN_OPACITY = {
    WeatherMotif.clear: 1,
    WeatherMotif.partly_cloudy: 0.85,
    WeatherMotif.overcast: 0.55,
    WeatherMotif.showers: 0.6,
    WeatherMotif.rain: 0.45,
    WeatherMotif.snow: 0.55,
    WeatherMotif.fog: 0.5,
}


def date_line(day: date) -> str:
    return f"{day:%A} · {day:%B} {day.day} {day.year}"


def scene_for(motif: WeatherMotif, weather: DayWeather | None, st: SunTimes) -> dict:
    """Pick which weather pieces appear. Clay stays the sun's colour only."""
    cond = {p.name: p.condition for p in (weather.periods if weather else [])}

    def wet(name: str) -> bool:
        return cond.get(name) in ("rain", "showers", "snow")

    precip_kind = "snow" if motif == WeatherMotif.snow else "rain"
    clouds: list[dict] = []
    birds = None
    ripples = False
    evening_cloud = False
    fog = motif == WeatherMotif.fog
    words: list[str] = []

    if motif in (WeatherMotif.rain, WeatherMotif.snow):
        for name, delay in (("morning", "d3"), ("midday", "d4")):
            clouds.append({"kind": precip_kind, "transform": _CLOUD_AT[name], "delay": delay,
                           "note": f"{precip_kind} over the {name}"})
        ripples = motif == WeatherMotif.rain
        evening_cloud = True
        words.append(f"a veiled sun behind {precip_kind} all day")
    elif motif == WeatherMotif.showers:
        wet_parts = [n for n in ("morning", "midday") if wet(n)] or ["midday"]
        for name in wet_parts:
            clouds.append({"kind": "rain", "transform": _CLOUD_AT[name], "delay": "d3" if name == "morning" else "d4",
                           "note": f"showers over the {name}"})
        dry = [n for n in ("morning", "midday") if n not in wet_parts]
        if dry:
            birds = {"transform": _BIRDS_AT[dry[0]], "note": f"dry {dry[0]}"}
        ripples = "midday" in wet_parts
        evening_cloud = wet("evening") or not cond
        words.append("a veiled sun with showers" + (f" over the {' and '.join(wet_parts)}" if wet_parts else ""))
    elif motif == WeatherMotif.overcast:
        for name, delay in (("morning", "d3"), ("midday", "d4")):
            clouds.append({"kind": "plain", "transform": _CLOUD_AT[name], "delay": delay, "note": f"cloud over the {name}"})
        evening_cloud = True
        words.append("a pale sun behind cloud")
    elif motif == WeatherMotif.partly_cloudy:
        clouds.append({"kind": "plain", "transform": _CLOUD_AT["midday"], "delay": "d4", "note": "a passing cloud at midday"})
        birds = {"transform": _BIRDS_AT["morning"], "note": "morning"}
        evening_cloud = cond.get("evening") in ("overcast", "partly_cloudy")
        words.append("sun with a passing cloud")
    elif motif == WeatherMotif.fog:
        clouds.append({"kind": "plain", "transform": _CLOUD_AT["midday"], "delay": "d4", "note": "cloud after the fog"})
        words.append("morning fog under a pale sun")
    else:  # clear
        birds = {"transform": _BIRDS_AT["morning"], "note": "clear morning"}
        words.append("a clear sun crossing the sky")

    words.append("moon and stars in the evening" + (" behind cloud" if evening_cloud else ""))
    rise_x = (st.rise_hours - min(7, int(st.rise_hours))) / (23 - min(7, int(st.rise_hours))) * 840
    return {
        "aria": "The day as a landscape: " + ", ".join(words),
        "sun_opacity": _SUN_OPACITY[motif],
        "sun_x": round(rise_x),
        "clouds": clouds,
        "birds": birds,
        "ripples": ripples,
        "fog": fog,
        "evening_cloud": evening_cloud,
    }


def link_text(text: str, phrase: str, url: str) -> Markup:
    """Escape the sentence, then turn the first match of the phrase into a link."""
    safe, ph = str(escape(text)), str(escape(phrase))
    i = safe.find(ph)
    if i < 0:
        return Markup(safe)
    a = f'<a href="{escape(url)}">{ph}</a>'
    return Markup(safe[:i] + a + safe[i + len(ph):])


def _num(h: float) -> float | int:
    return int(h) if float(h).is_integer() else round(h, 2)


def _js_hours(h: int, m: int) -> str:
    return f"{h}" if m == 0 else f"{h} + {m}/60"


@dataclass
class Page:
    html: str
    urls: list[str]


def render(
    day: date,
    content: BriefContent,
    st: SunTimes,
    weather: DayWeather | None,
    *,
    status: str = "fresh",
    stale_note: str | None = None,
) -> Page:
    by_kind = {s.kind: s for s in content.sections}
    sections = []
    for kind in SECTION_ORDER:
        if kind.value == "formula1":
            # Weather always sits between the news and the sport.
            sections.append({"title": "Weather", "line": weather_line(content.weather_line)})
        s = by_kind.get(kind)
        if s is None:
            continue
        sections.append({
            "title": SECTION_TITLES[kind],
            "entries": [{"url": i.url, "title": i.title, "html": link_text(i.text, i.link_phrase, i.url)} for i in s.items],
        })
    labels = act_labels(st)
    html = _env.get_template("brief.html.j2").render(
        meta={"date": day.isoformat(), "status": status},
        date_line=date_line(day),
        stale_note=stale_note,
        headline=content.headline,
        scene=scene_for(content.weather_motif, weather, st),
        acts=[{"label": labels[n], "text": a.text} for n, a in enumerate(content.acts)],
        sections=sections,
        sun={"rise_js": _js_hours(*st.rise_hm), "set_js": _js_hours(*st.set_hm)},
        marks=[[_num(m.hour), m.label] for m in sorted(content.marks, key=lambda m: m.hour)],
    )
    return Page(html=html, urls=[*content.urls(), YR_URL])


def weather_line(text: str) -> Markup:
    text = text.strip().rstrip(".")
    return Markup(f'{escape(text)} (<a href="{escape(YR_URL)}">Yr</a>).')
