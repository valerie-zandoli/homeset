"""Canned wger results for --mock runs and tests.  No network.

The page in mock_data/exerciseinfo_page.json is a trimmed copy of a live wger response
(muscles=4, language=2, equipment 3 and 7, read on 2026-10-13).  It includes exercises
that need a bench (equipment 8) and ones whose first translation is not English, so
the subset filter and the language rule are exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

from .wger import search_exercises

_PAGE = Path(__file__).parent / "mock_data" / "exerciseinfo_page.json"


class _Response:
    status_code = 200
    headers: dict = {}

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def mock_get(url, params, timeout):
    return _Response(json.loads(_PAGE.read_text()))


def mock_search(focus: str, equipment: list[str]) -> dict:
    return search_exercises(focus, equipment, get=mock_get, sleep=lambda s: None)
