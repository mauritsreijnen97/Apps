import pytest
from pydantic import ValidationError

from brief.schema import BriefContent


def test_fixture_is_valid(content):
    assert len(content.acts) == 3


@pytest.mark.parametrize("mutate,msg", [
    (lambda d: d["sections"][0]["items"][0].update(link_phrase="not in the text"), "link_phrase"),
    (lambda d: d.update(headline="Strike day."), "Maurits"),
    (lambda d: d["acts"].pop(), "three"),
    (lambda d: d.update(marks=[{"hour": 9 + i, "label": "x"} for i in range(4)]), "three marks"),
    (lambda d: d["sections"][1]["items"].pop(), "4 to 6"),
    (lambda d: d["marks"].append({"hour": 3, "label": "too early"}), "hour"),
    (lambda d: d["sections"][0]["items"][0].update(url="/relative"), "absolute"),
    (lambda d: d.update(weather_motif="sunny"), "weather_motif"),
    (lambda d: d.update(extra="nope"), "extra"),
])
def test_rejects(content_data, mutate, msg):
    mutate(content_data)
    with pytest.raises(ValidationError) as e:
        BriefContent.model_validate(content_data)
    assert msg.split()[0] in str(e.value) or msg in str(e.value)


def test_formula1_and_next_week_are_exclusive(content_data):
    item = content_data["sections"][0]["items"][0]
    content_data["sections"] += [{"kind": "formula1", "items": [item]}, {"kind": "next_week", "items": [item]}]
    with pytest.raises(ValidationError):
        BriefContent.model_validate(content_data)
