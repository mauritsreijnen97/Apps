import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from brief import gates
from brief.render import render
from conftest import DAY


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _route(self, head: bool):
        if self.path == "/ok":
            self.send_response(200)
        elif self.path == "/moved":
            self.send_response(301)
            self.send_header("Location", "/ok")
        elif self.path == "/no-head":
            self.send_response(405 if head else 200)
        elif self.path == "/walled":
            body = b"<title>Attention Required! | Cloudflare</title>"
            self.send_response(403)
            self.send_header("Content-Length", str(0 if head else len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
            return
        else:
            self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self._route(True)

    def do_GET(self):
        self._route(False)


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_em_dash_gate():
    assert gates.check_em_dash("a, b; c: d").ok
    r = gates.check_em_dash("strike day — again")
    assert not r.ok and "U+2014" in r.failures[0]


def test_url_gate(server, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    r = gates.check_urls([f"{server}/ok", f"{server}/moved", f"{server}/no-head", f"{server}/gone", f"{server}/walled"])
    assert len(r.failures) == 2 and r.dead == [f"{server}/gone", f"{server}/walled"]
    assert r.walled == [f"{server}/walled"] and "bot-wall" in r.failures[1]
    assert any("GET 200" in n and "/no-head" in n for n in r.notes)


def test_render_gate_passes_and_saves_screenshots(content, st, weather, tmp_path):
    page = tmp_path / "index.html"
    page.write_text(render(DAY, content, st, weather).html)
    r = gates.check_render(page, tmp_path / "shots", wait_ms=800, expected_marks=2)
    assert r.ok, r.failures
    assert sorted(Path(s).name for s in r.screenshots) == ["brief-390.png", "brief-960.png"]


def test_close_marks_do_not_collide(content_data, st, weather, tmp_path):
    from brief.schema import BriefContent
    content_data["marks"] = [{"hour": 14, "label": "march, 2 PM"}, {"hour": 14.25, "label": "rally, 2:15 PM"}]
    page = tmp_path / "index.html"
    page.write_text(render(DAY, BriefContent.model_validate(content_data), st, weather).html)
    assert gates.check_render(page, None, wait_ms=800, expected_marks=2).ok


BAD = """<!doctype html><html><head><meta name=viewport content="width=device-width"></head>
<body style="margin:0"><h1 style="font-size:40px;line-height:1.15">{h1}</h1>{extra}
<svg viewBox="0 0 840 170" width="100%"><g id="marks" font-size="11">
<text x="100" y="50">overlapping label one</text><text x="110" y="52">overlapping label two</text></g></svg>
</body></html>"""


def test_render_gate_catches_problems(tmp_path):
    page = tmp_path / "bad.html"
    page.write_text(BAD.format(h1="Maurits, " + "a very long headline that wraps " * 4, extra='<div style="width:1400px">wide</div>'))
    r = gates.check_render(page, None, wait_ms=100)
    joined = "\n".join(r.failures)
    assert "horizontal scroll" in joined
    assert "mark labels overlap" in joined
    assert "390px: headline takes" in joined
