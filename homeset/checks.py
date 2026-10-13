"""Output checks.  They apply to plans only (diagram v3).

Hand-offs, error messages, and the one clarifying question skip these checks and go
straight to the user, because a refusal has no exercises and no total time and would
fail every check.

A plan passes when:
  1. the format is exact (PRD 3b OUTPUT FORMAT)
  2. every exercise name came back from search_exercises in this request
  3. the equipment matches what the user has (bodyweight always allowed)
  4. the total time is within 5 minutes of the time requested, and the stated total
     matches the code's own sum
  5. the safety line is present
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .labels import BODYWEIGHT_ID
from .plan_time import BAND_MINUTES, calculate_plan_time

from .messages import HANDOFF as HANDOFF_SENTENCE
from .messages import PREFIXES

SAFETY_LINE = "Stop if anything hurts.  For pain or injury, see a doctor or physical therapist."
UNREACHABLE_PREFIX = PREFIXES["error"][0]

_LINE1 = re.compile(r"^HomeSet plan: (\d+(?:\.\d+)?) min, (.+), (.+)$")
# An exercise line is "<n>. <name> (<equipment>): <sets> sets x <reps> reps, rest <seconds> s".
# Names can contain parentheses ("Pike Hold (Floor)") and so can equipment text
# ("none (bodyweight exercise)"), so the name is matched against the names wger returned
# for this request, longest first.  When no known name matches, the line is split at the
# first " (" and the name check reports the unknown name.
_EXERCISE = re.compile(r"^(\d+)\. (.+): (\d+) sets x (\d+) reps, rest (\d+) s$")
_TOTAL = re.compile(r"^Total time: (\d+(?:\.\d+)?) min \(calculated\)$")


def _norm(text: str) -> str:
    return " ".join(text.split())


@dataclass
class ParsedPlan:
    minutes_line: float
    exercises: list[dict]  # name, equipment_text, sets, reps, rest_seconds
    stated_total: float


def classify(text: str) -> str:
    """'handoff', 'error', 'question', or 'plan' (anything else is checked as a plan)."""
    t = _norm(text)
    if t == _norm(HANDOFF_SENTENCE):
        return "handoff"
    if t.lower().startswith(UNREACHABLE_PREFIX.lower()):
        return "error"
    if t.startswith("HomeSet plan:"):
        return "plan"
    if any(t.lower().startswith(p.lower()) for p in PREFIXES["question"]) or t.endswith("?"):
        return "question"
    return "plan"  # anything else is checked as a plan, and fails the format check


def _split_name(body: str, known_names: list[str]) -> tuple[str, str] | None:
    """Split "<name> (<equipment>)" into (name, equipment text), using known names first."""
    if not body.endswith(")"):
        return None
    lowered = body.lower()
    for name in sorted(known_names, key=len, reverse=True):
        prefix = name.lower() + " ("
        if lowered.startswith(prefix):
            return body[: len(name)], body[len(prefix) : -1]
    head, sep, tail = body.partition(" (")
    return (head, tail[:-1]) if sep else None


def parse_plan(text: str, known_names: list[str] | None = None) -> ParsedPlan:
    """Parse the exact OUTPUT FORMAT.  Raises ValueError naming the first thing that is off."""
    known_names = known_names or []
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 4:
        raise ValueError("the answer is too short to be a plan")
    m = _LINE1.match(lines[0])
    if not m:
        raise ValueError("line 1 is not 'HomeSet plan: <minutes> min, <equipment>, <focus>'")
    exercises = []
    for ln in lines[1:-2]:
        em = _EXERCISE.match(ln)
        if not em:
            raise ValueError(f"not an exercise line: {ln!r}")
        split = _split_name(em.group(2).strip(), known_names)
        if split is None:
            raise ValueError(f"not an exercise line (needs '<name> (<equipment>)'): {ln!r}")
        exercises.append(
            {
                "name": split[0].strip(),
                "equipment_text": split[1].strip(),
                "sets": int(em.group(3)),
                "reps": int(em.group(4)),
                "rest_seconds": int(em.group(5)),
            }
        )
    if not exercises:
        raise ValueError("the plan has no exercise lines")
    tm = _TOTAL.match(lines[-2])
    if not tm:
        raise ValueError("the second-to-last line is not 'Total time: <minutes> min (calculated)'")
    return ParsedPlan(float(m.group(1)), exercises, float(tm.group(1)))


def check_plan(
    text: str,
    known_exercises: dict[str, list[int]],
    owned_equipment_ids: set[int],
    requested_minutes: float | None,
) -> list[str]:
    """Return a list of failure messages; an empty list means the plan passes.

    known_exercises: exercise name (any case) -> its equipment ids, from this request's
    search_exercises results.
    """
    failures: list[str] = []
    try:
        plan = parse_plan(text, list(known_exercises))
    except ValueError as err:
        return [f"format: {err}"]

    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if _norm(lines[-1]) != _norm(SAFETY_LINE):
        failures.append("safety line: the last line is not the exact safety line")

    known = {name.lower(): ids for name, ids in known_exercises.items()}
    allowed = set(owned_equipment_ids) | {BODYWEIGHT_ID}
    for ex in plan.exercises:
        ids = known.get(ex["name"].lower())
        if ids is None:
            failures.append(f"name: {ex['name']!r} did not come back from search_exercises")
        elif not set(ids) <= allowed:
            failures.append(f"equipment: {ex['name']!r} needs equipment the user does not have")

    computed = calculate_plan_time(plan.exercises)
    if abs(computed - plan.stated_total) > 0.6:
        failures.append(f"total: stated {plan.stated_total} min but the code adds up to {computed} min")
    target = requested_minutes if requested_minutes is not None else plan.minutes_line
    if abs(computed - target) > BAND_MINUTES:
        failures.append(f"time: {computed} min is more than {BAND_MINUTES} min from the {target} min requested")
    return failures
