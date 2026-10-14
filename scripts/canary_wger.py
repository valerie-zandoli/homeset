"""Pre-demo canary:  a known question to wger that must come back with a known-sized answer.

A run that "succeeds" can still be wrong when wger answers 200 with a changed shape, a frozen
copy, or an empty list.  The agent now treats an unreadable page as a failure, but only a
known-answer probe proves the live service still returns what the design assumes.  This asks
each focus label with a mat and dumbbells (read-only GET requests, nothing saved) and checks:

  - the call returns (no WgerUnavailable)
  - no result had an unreadable English name  (`unreadable` is 0)
  - at least the floor of usable exercises came back  (half of the live count on 2026-10-14)
  - the call finished inside the 30 second deadline

Run:  python scripts/canary_wger.py        (exit 0 = all pass, 1 = a check failed, 2 = wger unreachable)

Limits:  it catches a changed shape or a collapsed data set, not a record that is plausible and
wrong, and it does not read the text.  Run `scripts/scan_wger_text.py` for the text.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from homeset.wger import MAX_SECONDS_PER_SEARCH, WgerUnavailable, search_exercises  # noqa: E402

EQUIPMENT = ["mat", "dumbbells"]
PACE_SECONDS = 0.25  # politeness toward a free public service

# Half of the usable exercises returned on 2026-10-14 (legs 100, thighs 68, glutes 39, calves 21,
# core 52, chest 29, back 41, shoulders 34, arms 56, upper body 111, full body 134, cardio 22).
FLOORS = {
    "legs": 50, "thighs": 30, "glutes": 15, "calves": 10, "core": 25, "chest": 10,
    "back": 20, "shoulders": 15, "arms": 25, "upper body": 50, "full body": 60, "cardio": 10,
}


def paced_get(url, params, timeout):
    time.sleep(PACE_SECONDS)
    return requests.get(url, params=params, timeout=timeout)


def main() -> int:
    failures = 0
    for focus, floor in FLOORS.items():
        started = time.monotonic()
        try:
            result = search_exercises(focus, EQUIPMENT, get=paced_get)
        except WgerUnavailable as err:
            print(f"FAIL  {focus:11} wger answered but not usably:  {err}")
            failures += 1
            continue
        except requests.RequestException as err:
            print(f"Could not read wger:  {type(err).__name__}")
            return 2
        seconds = time.monotonic() - started
        groups = result["groups"]
        kept = sum(len(g["exercises"]) for g in groups)
        unreadable = sum(g["unreadable"] for g in groups)
        problems = []
        if unreadable:
            problems.append(f"{unreadable} unreadable")
        if kept < floor:
            problems.append(f"{kept} usable, floor {floor}")
        if seconds > MAX_SECONDS_PER_SEARCH:
            problems.append(f"{seconds:.0f} s, deadline {MAX_SECONDS_PER_SEARCH} s")
        status = "FAIL" if problems else "ok  "
        failures += bool(problems)
        print(f"{status}  {focus:11} usable {kept:3} (floor {floor:2})  unreadable {unreadable}  {seconds:4.1f} s"
              + (f"  <- {', '.join(problems)}" if problems else ""))
    print(f"\n{len(FLOORS) - failures} of {len(FLOORS)} focus labels passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
