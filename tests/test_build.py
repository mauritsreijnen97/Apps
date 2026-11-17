import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from brief import build, config
from brief.history import History
from brief.schema import BriefContent
from conftest import FIX


@pytest.fixture
def dist(tmp_path, monkeypatch):
    d = tmp_path / "dist"
    monkeypatch.setattr(config, "DIST", d)
    monkeypatch.setattr(config, "SCREENSHOTS", tmp_path / "shots")
    return d


def _run(*extra):
    return build.main(["--date", "2026-11-17", "--content", str(FIX / "content_2026-11-17.json"),
                       "--weather-json", str(FIX / "met_complete.json"), "--no-link-check", *extra])


def test_full_offline_build_then_skip(dist, capsys):
    assert _run() == 0
    html = (dist / "index.html").read_text()
    assert '<meta name="brief-status" content="fresh">' in html
    assert (dist / "archive" / "2026-11-17.html").exists()
    assert len(json.loads((dist / "history.json").read_text())["days"]["2026-11-17"]) == 7
    rec = json.loads((dist / "build.json").read_text())
    assert rec["status"] == "fresh"
    assert _run() == 0
    assert "already built" in capsys.readouterr().out


def test_gate_failure_falls_back_to_previous_page(dist, tmp_path):
    assert _run() == 0
    bad = json.loads((FIX / "content_2026-11-17.json").read_text())
    bad["headline"] = "Maurits, strike day — again"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    code = build.main(["--date", "2026-11-18", "--content", str(p), "--weather-json", str(FIX / "met_complete.json"),
                       "--no-link-check"])
    assert code == 3
    html = (dist / "index.html").read_text()
    assert "not updated today" in html and 'content="stale"' in html
    rec = json.loads((dist / "build.json").read_text())
    assert rec["status"] == "stale" and len(rec["attempts"]) == 2
    assert "U+2014" in rec["attempts"][0]["gates"]["failures"][0]
    # a stale page never counts as built, so the next scheduled run tries again
    assert not build.already_built(dist, date(2026, 11, 18))


def test_no_previous_page_means_failure(dist, tmp_path):
    p = tmp_path / "bad.json"
    bad = json.loads((FIX / "content_2026-11-17.json").read_text())
    bad["weather_line"] = "rain — lots"
    p.write_text(json.dumps(bad))
    assert build.main(["--date", "2026-11-17", "--content", str(p), "--no-link-check",
                       "--weather-json", str(FIX / "met_complete.json")]) == 1


def test_make_stale_is_idempotent():
    html = '<meta name="brief-status" content="fresh">\n<p class="date rise d1">Monday · March 2 2026</p>'
    once = build.make_stale(html)
    assert build.make_stale(once) == once and once.count("not updated today") == 1


def test_tidy_drops_repeats_but_keeps_coming_up(content_data):
    extra = dict(content_data["sections"][1]["items"][0], url="https://example.org/fifth")
    content_data["sections"][1]["items"].append(extra)
    content = BriefContent.model_validate(content_data)
    repeat = content.sections[1].items[0].url
    tunnel = content.sections[0].items[1].url
    trimmed, dropped = build.tidy(content, [repeat, tunnel], set())
    assert len(trimmed.sections[1].items) == 4
    assert any(repeat in d for d in dropped)
    assert tunnel in trimmed.urls()


def test_tidy_too_few_left_raises(content):
    urls = [i.url for i in content.sections[1].items[:2]]
    with pytest.raises(Exception):
        build.tidy(content, urls, set())


def test_tidy_drops_unsourced(content):
    sources = {build._norm(u) for u in content.urls() if "tradingview" not in u}
    trimmed, dropped = build.tidy(content, [], sources)
    assert not any("tradingview" in u for u in trimmed.urls())
    assert any("not found in search results" in d for d in dropped)


def test_history_window(tmp_path):
    h = History(tmp_path / "h.json")
    h.record(date(2026, 11, 1), ["https://a"])
    h.record(date(2026, 11, 17), ["https://b"])
    h.record(date(2026, 11, 18), ["https://c"])
    assert h.recent(date(2026, 11, 18)) == ["https://b"]  # 1 Nov fell out of the 14-day window
    h.save()
    assert History(tmp_path / "h.json").recent(date(2026, 11, 19)) == ["https://b", "https://c"]


def test_dead_link_drops_the_item_not_the_page(dist, monkeypatch, content_data, tmp_path):
    from brief import gates
    content_data["sections"][1]["items"].append(dict(content_data["sections"][1]["items"][0], url="https://walled.example/x"))
    p = tmp_path / "c.json"
    p.write_text(json.dumps(content_data))

    def fake_check(urls):
        r = gates.GateReport()
        for u in urls:
            if "walled.example" in u:
                r.failures.append(f"dead link [GET 403 bot-wall] {u}")
                r.dead.append(u)
                r.walled.append(u)
            else:
                r.notes.append(f"ok {u}")
        return r

    monkeypatch.setattr(gates, "check_urls", fake_check)
    code = build.main(["--date", "2026-11-17", "--content", str(p), "--weather-json", str(FIX / "met_complete.json")])
    assert code == 0
    html = (dist / "index.html").read_text()
    assert "walled.example" not in html
    assert json.loads((dist / "blocked-hosts.json").read_text()) == {"walled.example": "2026-11-17"}
    rec = json.loads((dist / "build.json").read_text())
    assert any("link failed the check" in d for d in rec["attempts"][0]["dropped"])


def test_dead_link_that_thins_a_section_retries_with_feedback(dist, monkeypatch):
    from brief import gates

    def fake_check(urls):
        r = gates.GateReport()
        bad = [u for u in urls if "fool.com" in u]
        r.dead, r.failures = bad, [f"dead link [GET 404] {u}" for u in bad]
        return r

    monkeypatch.setattr(gates, "check_urls", fake_check)
    code = build.main(["--date", "2026-11-17", "--content", str(FIX / "content_2026-11-17.json"),
                       "--weather-json", str(FIX / "met_complete.json")])
    assert code == 1  # four items minus one is too few, twice, and no older page exists
    rec = json.loads((dist / "build.json").read_text())
    assert "4 to 6" in rec["attempts"][1]["error"]


def test_blocked_hosts_window(tmp_path):
    b = build.BlockedHosts(tmp_path / "b.json")
    b.add(["https://www.france24.com/en/x", "https://old.example/y"], date(2026, 8, 1))
    b.add(["https://www.france24.com/en/z"], date(2026, 11, 17))
    assert b.domains(date(2026, 11, 18)) == ["france24.com"]
