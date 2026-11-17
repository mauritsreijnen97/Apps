import re

from brief.config import REFERENCE, YR_URL
from brief.render import date_line, link_text, render, scene_for
from brief.schema import BriefContent, WeatherMotif
from conftest import DAY


def _style(html: str) -> str:
    return re.search(r"<style>.*?</style>", html, re.S).group(0)


def test_style_block_is_byte_identical_to_reference(content, st, weather):
    ref = REFERENCE.read_text(encoding="utf-8")
    out = render(DAY, content, st, weather).html
    assert _style(out) == _style(ref)
    assert "@font-face{font-family:\"Fraunces\"" in _style(out)


def test_head_only_adds_meta_tags(content, st, weather):
    ref = REFERENCE.read_text(encoding="utf-8")
    out = render(DAY, content, st, weather).html
    ref_head = ref[: ref.index("</head>")]
    out_head = out[: out.index("</head>")]
    stripped = re.sub(r'\n<meta name="(brief-date|brief-status|robots)" content="[^"]*">', "", out_head)
    assert stripped == ref_head
    assert '<meta name="brief-date" content="2026-11-17">' in out_head
    assert '<meta name="brief-status" content="fresh">' in out_head


def test_dynamic_parts(content, st, weather):
    html = render(DAY, content, st, weather).html
    assert '<p class="date rise d1">Tuesday · November 17 2026</p>' in html
    assert "<h1 class=\"rise d2\">Maurits, it is strike day, but lines L and U run normally.</h1>" in html
    assert "var SUNRISE = 8 + 3/60, SUNSET = 17 + 8/60;" in html
    assert 'var MARKS = [[11, "stations shut, 11 AM"], [14, "march, 2 PM"]]' in html
    assert "<b>Sunrise 8:03 to 12 PM</b>" in html and "<b>12 to 5:08 PM</b>" in html and "<b>5:08 PM onward</b>" in html
    assert html.count('<div class="act rise d') == 3
    # sections in fixed order, weather between the news and the sport
    titles = re.findall(r"<h2>(.*?)</h2>", html)
    assert titles == ["Coming up today", "Worth knowing", "Weather"]
    assert f'(<a href="{YR_URL}">Yr</a>).</p>' in html
    assert html.count("<li><div><a class=\"t\"") == 7
    assert "—" not in html


def test_reference_animations_survive(content, st, weather):
    html = render(DAY, content, st, weather).html
    for needle in ('class="terrain"', 'id="sun"', 'class="rays"', 'class="glow"', 'id="night"', 'id="now"',
                   "requestAnimationFrame", "setInterval", "Europe/Paris", "class:'pulse'", 'id="marks"'):
        assert needle in html


def test_text_is_escaped(content_data, st, weather):
    content_data["headline"] = "Maurits, <script>alert(1)</script> & co"
    item = content_data["sections"][1]["items"][0]
    item["title"] = 'Tom & "Jerry" <b>'
    html = render(DAY, BriefContent.model_validate(content_data), st, weather).html
    assert "<script>alert(1)</script>" not in html
    assert "Maurits, &lt;script&gt;alert(1)&lt;/script&gt; &amp; co" in html
    assert "Tom &amp; &#34;Jerry&#34; &lt;b&gt;" in html


def test_marks_json_cannot_break_out_of_script(content_data, st, weather):
    content_data["marks"] = [{"hour": 15, "label": "</script><b>x"}]
    html = render(DAY, BriefContent.model_validate(content_data), st, weather).html
    assert "</script><b>x" not in html


def test_link_phrase_becomes_the_link():
    out = str(link_text("Prices rose 5% & more in Paris.", "rose 5% & more", "https://e.x/a?b=1&c=2"))
    assert out == 'Prices <a href="https://e.x/a?b=1&amp;c=2">rose 5% &amp; more</a> in Paris.'


def test_date_line():
    from datetime import date
    assert date_line(date(2026, 3, 2)) == "Monday · March 2 2026"


def test_motif_rain_dims_sun_adds_ripples(st, weather):
    s = scene_for(WeatherMotif.rain, weather, st)
    assert s["sun_opacity"] == 0.45 and s["ripples"] and s["birds"] is None
    assert [c["kind"] for c in s["clouds"]] == ["rain", "rain"] and s["evening_cloud"]


def test_motif_clear_drops_clouds(st, weather, content, ):
    s = scene_for(WeatherMotif.clear, weather, st)
    assert s["sun_opacity"] == 1 and not s["clouds"] and not s["ripples"] and s["birds"]
    html = render(DAY, content.model_copy(update={"weather_motif": WeatherMotif.clear}), st, weather).html
    assert 'id="sun" transform="translate(' in html and "opacity=\".45\"" not in html
    assert "class=\"ripple\"" not in html and "M150 52" not in html and "class=\"wing\"" in html


def test_motif_showers_follow_the_wet_parts(st, weather):
    # fixture day: dry morning, showers from midday
    s = scene_for(WeatherMotif.showers, weather, st)
    assert [c["note"] for c in s["clouds"]] == ["showers over the midday"]
    assert s["birds"]["note"] == "dry morning" and s["ripples"]


def test_only_clay_is_accent(content, st, weather):
    for motif in WeatherMotif:
        html = render(DAY, content.model_copy(update={"weather_motif": motif}), st, weather).html
        body = html[html.index("<body>"):]
        colours = set(re.findall(r"#[0-9A-Fa-f]{6}", body))
        assert colours <= {"#C6613F", "#2E2C27", "#B4B3A8", "#F9F9F7", "#6B6A63"}, motif
