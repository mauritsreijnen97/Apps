import json
from datetime import date
from pathlib import Path

import pytest

from brief.schema import BriefContent
from brief.sun import sun_times
from brief.weather import load_fixture, summarise

FIX = Path(__file__).parent / "fixtures"
DAY = date(2026, 11, 17)


@pytest.fixture
def content_data() -> dict:
    return json.loads((FIX / "content_2026-11-17.json").read_text())


@pytest.fixture
def content(content_data) -> BriefContent:
    return BriefContent.model_validate(content_data)


@pytest.fixture
def st():
    return sun_times(DAY)


@pytest.fixture
def weather(st):
    return summarise(load_fixture(FIX / "met_complete.json"), date(2026, 11, 18), sun_times(date(2026, 11, 18)))


@pytest.fixture(autouse=True)
def fast_render(monkeypatch):
    monkeypatch.setenv("BRIEF_RENDER_WAIT_MS", "800")
