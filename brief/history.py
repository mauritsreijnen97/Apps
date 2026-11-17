"""dist/history.json: which URLs went out on which day, so stories never repeat."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import HISTORY_DAYS


class History:
    def __init__(self, path: Path):
        self.path = path
        self.days: dict[str, list[str]] = {}
        if path.exists():
            self.days = json.loads(path.read_text()).get("days", {})

    def recent(self, before: date) -> list[str]:
        """URLs from earlier pages, oldest first, excluding `before` itself."""
        out: list[str] = []
        for d in sorted(self.days):
            if d < before.isoformat():
                out += self.days[d]
        return list(dict.fromkeys(out))

    def record(self, day: date, urls: list[str]) -> None:
        self.days[day.isoformat()] = list(dict.fromkeys(urls))
        cutoff = (day - timedelta(days=HISTORY_DAYS)).isoformat()
        self.days = {d: u for d, u in self.days.items() if d >= cutoff}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"days": self.days}, indent=1, sort_keys=True) + "\n")
