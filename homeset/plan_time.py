"""calculate_plan_time: adds up a plan's time in code, so the model never does the arithmetic.

Time model (an assumption to tune after the first test run; see PRD Section 3a):
  - 3 seconds per rep
  - the rest time given for each set
  - 30 seconds between exercises
A plan passes when its total is within 5 minutes of the time the user asked for.  The
agent aims for 2 minutes (AIM_MINUTES) so that a plan does not stop at the edge of the band:
in 21 live plans on 2026-10-13/14 the mean was +0.8 minutes but the spread ran from -3.0
to +4.8, and the prompt only asked the model to stop once it was inside the band.

Timed moves such as planks are a non-goal for version 1:  wger does not mark which
exercises are timed, so every exercise is counted by reps.
"""

from __future__ import annotations

from typing import Iterable, Mapping

SECONDS_PER_REP = 3
TRANSITION_SECONDS = 30
BAND_MINUTES = 5  # the pass rule (PRD success metric); do not change without the PRD
AIM_MINUTES = 2  # what the prompt asks the model to land within


def calculate_plan_time(exercises: Iterable[Mapping[str, int]]) -> float:
    """Total minutes for a plan.

    Each exercise needs "sets", "reps", and "rest_seconds" (whole, non-negative numbers).
    Each set is followed by its rest; exercises are separated by a transition.
    Returns minutes rounded to one decimal.  Raises ValueError for bad input.
    """
    items = list(exercises)
    if not items:
        raise ValueError("a plan needs at least one exercise")
    seconds = 0
    for i, ex in enumerate(items, start=1):
        try:
            sets, reps, rest = int(ex["sets"]), int(ex["reps"]), int(ex["rest_seconds"])
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(f"exercise {i} needs sets, reps, and rest_seconds") from err
        if min(sets, reps, rest) < 0:
            raise ValueError(f"exercise {i} has a negative number")
        seconds += sets * reps * SECONDS_PER_REP + sets * rest
    seconds += TRANSITION_SECONDS * (len(items) - 1)
    return round(seconds / 60, 1)


def within_band(total_minutes: float, requested_minutes: float, band: float = BAND_MINUTES) -> bool:
    return abs(total_minutes - requested_minutes) <= band
