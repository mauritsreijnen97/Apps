PY ?= python3
PORT ?= 8000

.PHONY: build preview check test gates install offline

install:            ## install Python deps and the Playwright browser
	$(PY) -m pip install -r requirements.txt
	$(PY) -m playwright install chromium

build:              ## build today's page (needs ANTHROPIC_API_KEY); skips if already built
	$(PY) -m brief.build

preview:            ## serve dist/ at http://localhost:$(PORT)
	$(PY) -m http.server $(PORT) --directory dist

check: test gates   ## run the test suite, then the gates on dist/index.html

test:
	$(PY) -m pytest -q

gates:
	@if [ -f dist/index.html ]; then $(PY) -m brief.gates dist/index.html; else echo "no dist/index.html yet, skipping gates"; fi

offline:            ## render the fixture page into dist-offline/ (no API key, no network)
	BRIEF_DIST=dist-offline BRIEF_SCREENSHOTS=screenshots-offline $(PY) -m brief.build --force --date 2026-11-17 --content tests/fixtures/content_2026-11-17.json \
		--weather-json tests/fixtures/met_complete.json --no-link-check
