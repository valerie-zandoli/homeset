"""Command line:  python -m homeset "I have 20 minutes, a mat, and dumbbells.  Work on legs."

Add --mock to use canned wger data instead of the network (the model call still needs
the API key in .env).
"""

from __future__ import annotations

import sys

from .agent import run_once


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print('usage: python -m homeset "your request" [--mock]')
        return 2
    search_fn = None
    if "--mock" in argv:
        from .mock_wger import mock_search

        search_fn = mock_search
        print("[MOCK DATA: canned wger results]\n")
    outcome = run_once(" ".join(args), search_fn)
    print(f"[{outcome.kind}]\n")
    print(outcome.text)
    for failure in outcome.failures:
        print(f"  failed check: {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
