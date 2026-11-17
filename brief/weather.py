"""MET Norway Locationforecast for Saint-Cloud, reduced to what the page needs."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import requests

from .config import LAT, LON, MET_URL, TZ, USER_AGENT
from .sun import SunTimes

# Ordered from most to least weather-defining.
_SEVERITY = ["snow", "rain", "showers", "fog", "overcast", "partly_cloudy", "clear"]


def _category(symbol: str | None, cloud: float | None) -> str:
    s = (symbol or "").split("_")[0]
    if "snow" in s or "sleet" in s:
        return "snow"
    if "showers" in s:
        return "showers"
    if "rain" in s or "thunder" in s:
        return "rain"
    if s == "fog":
        return "fog"
    if s == "cloudy":
        return "overcast"
    if s == "partlycloudy":
        return "partly_cloudy"
    if s in ("clearsky", "fair"):
        return "clear"
    if cloud is None:
        return "unknown"
    return "clear" if cloud < 25 else "partly_cloudy" if cloud < 70 else "overcast"


@dataclass
class Period:
    name: str
    start: float
    end: float
    condition: str = "unknown"
    temp_min: float | None = None
    temp_max: float | None = None
    precipitation_mm: float = 0.0
    hours: int = 0

    @property
    def wet(self) -> bool:
        return self.condition in ("rain", "showers", "snow")


@dataclass
class DayWeather:
    day: str
    temp_min: float | None
    temp_max: float | None
    precipitation_mm: float
    wind_max_kmh: float | None
    gust_max_kmh: float | None
    periods: list[Period] = field(default_factory=list)
    updated_at: str | None = None

    def suggested_motif(self) -> str:
        known = [p for p in self.periods if p.condition != "unknown"]
        if not known:
            return "overcast"
        conds = [p.condition for p in known]
        if "snow" in conds:
            return "snow"
        wet = [p for p in known if p.wet]
        if len(wet) == len(known) and len(known) >= 2:
            return "rain"
        if wet:
            return "showers"
        if conds.count("fog") * 2 >= len(conds):
            return "fog"
        worst = min(conds, key=_SEVERITY.index)
        return worst if worst in ("overcast", "partly_cloudy", "clear") else "overcast"

    def as_prompt(self) -> str:
        def t(v):
            return "n/a" if v is None else f"{v:.0f}°C"
        lines = [
            f"Day: {self.day} (MET Norway, updated {self.updated_at})",
            f"Temperature {t(self.temp_min)} to {t(self.temp_max)}, precipitation {self.precipitation_mm:.1f} mm",
            f"Max wind {self.wind_max_kmh or 0:.0f} km/h" + (f", gusts {self.gust_max_kmh:.0f} km/h" if self.gust_max_kmh else ""),
        ]
        for p in self.periods:
            lines.append(
                f"- {p.name} ({p.start:.2f}h to {p.end:.2f}h): {p.condition}, "
                f"{t(p.temp_min)} to {t(p.temp_max)}, {p.precipitation_mm:.1f} mm"
            )
        lines.append(f"Suggested motif from the data: {self.suggested_motif()}")
        return "\n".join(lines)

    def to_json(self) -> dict:
        return asdict(self)


def fetch_forecast(session: requests.Session | None = None) -> dict:
    http = session or requests
    r = http.get(
        MET_URL,
        params={"lat": f"{LAT:.4f}", "lon": f"{LON:.4f}"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def summarise(data: dict, day: date, st: SunTimes) -> DayWeather:
    """Turn the hourly series into day totals plus morning, midday and evening."""
    rise, sset = st.rise_hours, st.set_hours
    periods = [Period("morning", rise, 12.0), Period("midday", 12.0, sset), Period("evening", sset, 23.0)]
    temps: list[float] = []
    winds: list[float] = []
    gusts: list[float] = []
    precip = 0.0
    per_cond: dict[str, list[tuple[str, float | None]]] = {p.name: [] for p in periods}

    for row in data["properties"]["timeseries"]:
        t = datetime.fromisoformat(row["time"].replace("Z", "+00:00")).astimezone(TZ)
        if t.date() != day:
            continue
        inst = row["data"]["instant"]["details"]
        n1 = row["data"].get("next_1_hours")
        if n1 is None:
            continue  # beyond the hourly horizon; six-hour steps would double count
        h = t.hour + t.minute / 60
        temp = inst.get("air_temperature")
        mm = n1.get("details", {}).get("precipitation_amount", 0.0) or 0.0
        if temp is not None:
            temps.append(temp)
        if inst.get("wind_speed") is not None:
            winds.append(inst["wind_speed"] * 3.6)
        if inst.get("wind_speed_of_gust") is not None:
            gusts.append(inst["wind_speed_of_gust"] * 3.6)
        precip += mm
        for p in periods:
            if p.start <= h < p.end or (p.name == "morning" and rise - 1 <= h < p.start):
                p.hours += 1
                p.precipitation_mm += mm
                if temp is not None:
                    p.temp_min = temp if p.temp_min is None else min(p.temp_min, temp)
                    p.temp_max = temp if p.temp_max is None else max(p.temp_max, temp)
                per_cond[p.name].append((n1.get("summary", {}).get("symbol_code"), inst.get("cloud_area_fraction")))
                break

    for p in periods:
        cats = [_category(s, c) for s, c in per_cond[p.name]]
        cats = [c for c in cats if c != "unknown"]
        if not cats:
            continue
        wet = [c for c in cats if c in ("rain", "showers", "snow")]
        if "snow" in wet:
            p.condition = "snow"
        elif len(wet) * 2 > len(cats) and p.precipitation_mm >= 1.0:
            p.condition = "rain"
        elif wet:
            p.condition = "showers"
        else:
            # The most common dry state wins; ties go to the cloudier one.
            p.condition = max(set(cats), key=lambda c: (cats.count(c), -_SEVERITY.index(c)))

    return DayWeather(
        day=day.isoformat(),
        temp_min=min(temps) if temps else None,
        temp_max=max(temps) if temps else None,
        precipitation_mm=round(precip, 1),
        wind_max_kmh=round(max(winds), 0) if winds else None,
        gust_max_kmh=round(max(gusts), 0) if gusts else None,
        periods=periods,
        updated_at=data["properties"].get("meta", {}).get("updated_at"),
    )


def load_fixture(path: Path) -> dict:
    return json.loads(path.read_text())
