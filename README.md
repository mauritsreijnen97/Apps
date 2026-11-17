# Apps

Small static sites served from GitHub Pages:

- `disneyland-paris/`, our Disneyland weekend guide
- `french-home/`, The French Country Club
- `morning-brief/`, a weekday page generated automatically (see below)

## Morning brief

One static HTML page, published every weekday before 05:50 Paris time, with no manual steps.
It shows the day as a landscape (a clay sun placed live on today's arc, weather motifs, timed
events on the line), three acts (morning, midday, evening), and short sourced notes underneath.

The design is `reference/brief-2026-11-17.html`. The template reuses its `<head>` and `<style>`
byte for byte (a test checks this), plus its SVG scene, animations, inline script and 640px rules.

### How a build works

`python -m brief.build` writes `dist/index.html`:

1. **Skip check.** If `dist/index.html` is already today's fresh page, it stops (exit 0).
2. **Sun.** Sunrise and sunset for Saint-Cloud (48.844, 2.219), computed locally with `astral`.
3. **Weather.** MET Norway Locationforecast (`api.met.no`, with an identifying User-Agent),
   reduced to morning (sunrise to noon), midday (noon to sunset) and evening (sunset to 11 PM):
   conditions, min and max temperature, rainfall, wind. It also suggests a weather motif. Yr is
   linked as the source.
4. **Content.** Claude (`claude-opus-5-5`, effort `high`) with server-side web search and fetch.
   It returns strict JSON matching `brief/schema.py` (headline, three acts, marks, weather motif,
   weather line, sections of `{title, url, text, link_phrase}` items). The content rules are in
   the system prompt in `brief/content.py`. Python renders all markup, so the model never writes HTML.
5. **Clean-up.** Items are dropped if they repeat a URL from the last 14 days (`dist/history.json`),
   if their URL never appeared in the search results, or if their link fails the check.
6. **Gates.** The build fails if any of these fail:
   - no U+2014 (em dash) anywhere in the page
   - every link returns 2xx or 3xx (HEAD, falling back to GET)
   - Playwright at 960px and 390px, after waiting 4 s: no horizontal scroll, no overlapping mark
     labels in the SVG, headline within 3 lines at 390px, no script errors. Screenshots are saved to
     `screenshots/` and uploaded as workflow artifacts.
7. **Retry, then fall back.** If the model call or the gates fail, it retries once, and the failure
   reasons go back to Claude. If that also fails, the previous page is republished with a small grey
   "not updated today" note (exit 3), and the workflow run turns red so GitHub emails you.

What it adds beyond the spec:

- **Bot-wall memory.** Many news sites (Cloudflare, Akamai) answer automated link checks with a 403.
  Those hosts are recorded in `dist/blocked-hosts.json` and passed to web search as
  `blocked_domains`, so later runs stop citing them.
- **Collision-proof marks.** Two events close together lift the second label above its dot.
  Labels near either edge anchor inward.
- **Summer mornings.** The timeline starts before 7 AM when sunrise is earlier, so the sun isn't
  placed off the canvas in June.
- **Structured fallbacks.** Claude's server-side `fallbacks: "default"` is on, so a safety decline
  retries on a fallback model inside the same call.
- **Records.** `dist/build.json` records every attempt: token usage, searches, real cost, dropped
  items and gate results. `dist/archive/` keeps each day's page and JSON.

### Setup (once)

1. **Add the API key.** Go to Settings → Secrets and variables → Actions → New repository secret.
   Name it `ANTHROPIC_API_KEY` and paste a key from console.anthropic.com.
2. **Switch Pages to Actions.** Go to Settings → Pages → Build and deployment → Source, and choose
   **GitHub Actions**. The workflow now deploys the whole site (the other apps, plus the brief under
   `/morning-brief/`) on every push to `main` and every morning.
3. **Merge to `main`.** Scheduled workflows only run from the default branch.
4. **Do the first run by hand.** Go to Actions → Morning brief → Run workflow. It takes about
   5 to 10 minutes. The page appears at `https://<user>.github.io/<repo>/morning-brief/`, and the
   screenshots are under the run's artifacts.

State between runs (history, archive, last good page) lives on the `brief-data` branch, which the
workflow creates and updates itself.

**Privacy:** GitHub Pages sites on personal accounts are public. The page carries
`<meta name="robots" content="noindex">`, but anyone with the URL can read it.

### Schedule

The crons are `17 3`, `47 3` and `17 4` UTC, Monday to Friday. That is 04:17, 04:47 and 05:17
Paris time in winter, and 05:17, 05:47 and 06:17 in summer. The first run that succeeds publishes;
later runs see today's page and stop in seconds.

The spec asked for 04:40 and 05:40 UTC. In summer (UTC+2) those start at 06:40 and 07:40 Paris,
after the 05:50 deadline, and GitHub often starts scheduled runs 10 to 30 minutes late. The
earlier slots keep the summer page on time.

### Cost per run

These are estimates at Claude Opus 5.5 prices ($4 per million input tokens, $20 per million output
tokens, $10 per 1,000 web searches):

| | typical |
|---|---|
| Web searches (10 to 20) | $0.10 to $0.20 |
| Input tokens (search results re-read across the search loop, 150k to 400k) | $0.60 to $1.60 |
| Output and thinking (5k to 15k) | $0.10 to $0.30 |
| **One successful run** | **about $0.80 to $2.00** |
| A run that needs its retry | up to about $4 |

That is roughly $20 to $45 a month for about 22 weekdays. Skipped runs cost nothing. GitHub
Actions minutes are free for public repos and well within the free tier for private ones. The real
figure for each run is in `dist/build.json` (`usage.cost_usd`). Lower it with `BRIEF_EFFORT=medium`
or `BRIEF_MAX_SEARCHES=12`.

### Local development

```bash
make install      # pip install -r requirements.txt, then playwright install chromium
export ANTHROPIC_API_KEY=...
make build        # python -m brief.build (skips if today's page exists; add --force to rebuild)
make preview      # http://localhost:8000
make check        # tests, then the gates on dist/index.html
make offline      # render the fixture page into dist-offline/, no API key or network
```

Useful flags: `--date 2026-11-18`, `--force`, `--content file.json` (skip Claude and use your own
JSON), `--weather-json file.json`, `--no-link-check` (offline only; CI never uses it).

Layout:

```
brief/
  build.py      entry point and retry/fallback logic
  content.py    system prompt and the Claude call
  schema.py     pydantic contract (BriefContent)
  weather.py    MET Norway fetch and summary
  sun.py        astral sun times and act labels
  render.py     scene selection, linking, Jinja rendering
  gates.py      em dash, link and Playwright checks (also: python -m brief.gates dist/index.html)
  templates/    _head.html (reference head and style, verbatim) and brief.html.j2
tests/          template, schema, gates, build, sun and weather tests, with fixtures
.github/workflows/brief.yml
```
