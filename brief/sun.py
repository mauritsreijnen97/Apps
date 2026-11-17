"""Sunrise and sunset for Saint-Cloud, computed locally."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from astral import Observer
from astral.sun import sun

from .config import LAT, LON, TZ


@dataclass(frozen=True)
class SunTimes:
    sunrise: datetime
    sunset: datetime

    @property
    def rise_hm(self) -> tuple[int, int]:
        return self.sunrise.hour, self.sunrise.minute

    @property
    def set_hm(self) -> tuple[int, int]:
        return self.sunset.hour, self.sunset.minute

    @property
    def rise_hours(self) -> float:
        return self.sunrise.hour + self.sunrise.minute / 60

    @property
    def set_hours(self) -> float:
        return self.sunset.hour + self.sunset.minute / 60


def sun_times(day: date) -> SunTimes:
    s = sun(Observer(latitude=LAT, longitude=LON), date=day, tzinfo=TZ)
    # Round to the minute shown on the page.
    return SunTimes(s["sunrise"].replace(second=0, microsecond=0), s["sunset"].replace(second=0, microsecond=0))


def clock(h: int, m: int, *, suffix: bool = True) -> str:
    """8:02, 12 PM, 5:07 PM. Matches the reference page's style."""
    h12 = h % 12 or 12
    core = f"{h12}" if m == 0 else f"{h12}:{m:02d}"
    if not suffix:
        return core
    return f"{core} {'AM' if h < 12 else 'PM'}"


def act_labels(st: SunTimes) -> list[str]:
    rh, rm = st.rise_hm
    sh, sm = st.set_hm
    return [
        f"Sunrise {clock(rh, rm, suffix=False)} to 12 PM",
        f"12 to {clock(sh, sm)}",
        f"{clock(sh, sm)} onward",
    ]
