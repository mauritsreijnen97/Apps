"""Fixed settings. Everything that is not secret lives here."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DIST = Path(os.environ.get("BRIEF_DIST", ROOT / "dist"))
SCREENSHOTS = Path(os.environ.get("BRIEF_SCREENSHOTS", ROOT / "screenshots"))
TEMPLATES = Path(__file__).resolve().parent / "templates"
REFERENCE = ROOT / "reference" / "brief-2026-11-17.html"

TZ = ZoneInfo("Europe/Paris")
PLACE = "Saint-Cloud"
LAT, LON = 48.844, 2.219

MODEL = os.environ.get("BRIEF_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("BRIEF_EFFORT", "high")
MAX_SEARCHES = int(os.environ.get("BRIEF_MAX_SEARCHES", "20"))

# MET Norway asks every client to identify itself with a contact point.
USER_AGENT = "morning-brief/1.0 (+https://github.com/mauritsreijnen97/Apps)"
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
YR_URL = (
    "https://www.yr.no/en/forecast/daily-table/2-2981041/France/"
    "%C3%8Ele-de-France%20Region/Hauts-de-Seine/Saint-Cloud"
)

# How many days of past URLs are kept to stop repeats.
HISTORY_DAYS = 14

# Prices used for the cost line in build.json (USD).
PRICE_INPUT_PER_MTOK = 4.00
PRICE_OUTPUT_PER_MTOK = 20.00
PRICE_CACHE_READ_PER_MTOK = 0.20
PRICE_CACHE_WRITE_PER_MTOK = 5.00
PRICE_PER_SEARCH = 0.01
