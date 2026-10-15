"""Advanced moves blocked for beginners (the beginner-level rule, PRD 3d, rule B).

Every HomeSet plan is for a beginner.  The 2026-10-14 grading of request set A found two
plans that gave beginners moves that are too hard:  a04 "Single Arm Plank to Row 3x8" and
a06 "Pull-ups 3x8" (P3 N).  On 2026-10-15 Valerie and Yadan agreed on a named list of
advanced moves (rule B), with rule C as the tie-breaker for moves not on the list:  "a
first-time exerciser can do 8 clean reps unassisted."

The list holds only the moves both have ruled on.  Hollow Hold and Floor dips were ruled
fine for a beginner.  Chin-ups, pistol squats, muscle-ups, handstands, and burpees are on
the proposed list in docs/grading-sheet.md but not yet ruled on, so they are not blocked.

The check runs twice:  wger.py drops blocked moves before the model sees the results, and
checks.py rejects any plan that still names one (a backstop).

Matching ignores capitals, hyphens, and spacing.  Easier pull-up variants stay allowed:
"Assisted Pull-Up", "Australian pull-ups" (an inverted row), and "Pull-up Isometric Hold"
(not ruled on).  "Leg raises pull up bar" names the bar, not the move.
tests/test_advanced.py checks all 932 real English names and lists every name this blocks.

This module has no model or network code.
"""

from __future__ import annotations

import re

_BLOCKED: tuple[tuple[str, re.Pattern], ...] = (
    ("Single Arm Plank to Row", re.compile(r"\bplank[- ]?to[- ]?rows?\b", re.IGNORECASE)),
    ("Pull-ups", re.compile(r"\bpull[- ]?ups?\b(?![- ]?bar)", re.IGNORECASE)),
)

# Easier versions of a blocked move, allowed for a beginner.
_EASIER = re.compile(r"\bassisted\b|\baustralian\b|\bisometric\b|\bhold\b", re.IGNORECASE)


def blocked_move(name: str) -> str | None:
    """The blocked move this exercise name is a version of, or None when it is allowed."""
    if _EASIER.search(name):
        return None
    for move, pattern in _BLOCKED:
        if pattern.search(name):
            return move
    return None
