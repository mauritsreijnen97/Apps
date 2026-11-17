from datetime import date

from brief.sun import act_labels, clock, sun_times


def test_sun_times_saint_cloud():
    st = sun_times(date(2026, 11, 17))
    assert (st.sunrise.hour, st.sunset.hour) == (8, 17)
    summer = sun_times(date(2026, 6, 21))
    assert summer.sunrise.utcoffset().total_seconds() == 7200  # CEST
    assert act_labels(summer)[1].startswith("12 to 9:5")


def test_clock():
    assert clock(12, 0) == "12 PM" and clock(17, 7) == "5:07 PM" and clock(8, 2, suffix=False) == "8:02"


def test_weather_summary(weather):
    assert weather.temp_min is not None and weather.temp_max >= weather.temp_min
    assert [p.name for p in weather.periods] == ["morning", "midday", "evening"]
    assert weather.precipitation_mm >= 0
    assert weather.suggested_motif() in {"clear", "partly_cloudy", "overcast", "showers", "rain", "snow", "fog"}
    assert "Suggested motif" in weather.as_prompt()


def test_motif_rules(weather):
    for p in weather.periods:
        p.condition = "rain"
    assert weather.suggested_motif() == "rain"
    weather.periods[0].condition = "clear"
    assert weather.suggested_motif() == "showers"
    for p in weather.periods:
        p.condition = "clear"
    assert weather.suggested_motif() == "clear"
