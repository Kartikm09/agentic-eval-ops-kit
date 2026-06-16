"""I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Scenario


def load_scenario(path: str | Path) -> Scenario:
    with Path(path).open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return Scenario.from_dict(raw)


def load_scenarios_from_dir(path: str | Path) -> list[Scenario]:
    base = Path(path)
    return [load_scenario(item) for item in sorted(base.glob("*.json"))]
