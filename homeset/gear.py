"""Gear named inside an exercise name.

wger tags each exercise with equipment, but the tag is community data and can disagree with
the name:  "Biceps with TRX" is tagged bodyweight, "Medicine ball twist" is tagged Swiss
ball, and "Fly With Dumbbells, Decline Bench" is tagged plain bench (graded 2026-10-14, set A
cases a15, a11, and a05).  The equipment check trusts the tag, so a user with no equipment
could be handed an exercise that needs gear.

This module reads the gear words in the name and returns the equipment ids the name
implies.  The client adds them to the exercise's own ids, so the existing rules apply
unchanged:  the exercise is dropped unless the user owns every id (bodyweight is always
owned).  Gear with no label in the PRD table (TRX, machines, medicine balls, ropes) maps to
UNAVAILABLE_GEAR_ID, which no user owns, so such exercises are never offered.

Limits:  quantity ("two kettlebells") is not tracked except for the words "double" and
"two" before kettlebell, and a gear word used in a different sense would drop a real exercise.
tests/test_gear.py checks the 932 real English names and lists every name this changes.

This module has no model or network code.
"""

from __future__ import annotations

import re

UNAVAILABLE_GEAR_ID = 0  # no label, so no user owns it

# (equipment id, pattern).  Ids are the wger numbers in labels.EQUIPMENT_LABELS.
_RULES: tuple[tuple[int, re.Pattern], ...] = tuple(
    (gear_id, re.compile(pattern, re.IGNORECASE))
    for gear_id, pattern in (
        (3, r"\bdumb ?bells?\b|\bdumbells?\b"),
        (1, r"\bbarbells?\b"),
        (10, r"\bkettle ?bells?\b"),
        (11, r"\bbanded\b|\bbands?\b|\bresistance bands?\b"),
        (6, r"\bpull[- ]?ups?\b|\bchin[- ]?ups?\b"),
        (9, r"\bincline bench\b"),
        (8, r"\bbench\b|\bbenchpress\b"),
        (5, r"\bswiss ball\b|\bstability ball\b|\bexercise ball\b|\bphysio ball\b|\bgym ball\b"),
        (2, r"\bsz[- ]?bars?\b|\bez[- ]?bars?\b|\bcurl bars?\b"),
        (12, r"\bcables?\b"),
        (
            UNAVAILABLE_GEAR_ID,
            r"\btrx\b|\bsuspension\b|\bmachines?\b|\bsmith\b|\bropes?\b|\bsleds?\b|\bsandbags?\b|"
            r"\bplates?\b|\bmedicine ball\b|\bmed ball\b|\bbosu\b|\bsliders?\b|\bfoam roller\b|"
            r"\bab wheel\b|\bparallettes?\b|\brings?\b|\bdecline bench\b|\btrap bar\b|\bhex bar\b|"
            r"\blandmine\b|\b(?:double|two) kettle ?bells?\b",
        ),
    )
)

# "Dumbbell or Machine Calf Raise" offers the machine as an alternative; the first option is
# the one the plan relies on, so a gear word after "or" does not count.
_ALTERNATIVE = re.compile(
    r"\bor\s+(?:a\s+)?(?:machine|cable|barbell|kettle ?bell|band|bench|smith machine)\b", re.IGNORECASE
)
# "IT band" is a body part, not a resistance band.
_BODY_PART = re.compile(r"\b(?:it|iliotibial)\s+band\b", re.IGNORECASE)


def gear_ids_from_name(name: str) -> set[int]:
    """Equipment ids the exercise name implies (an empty set when it names no gear)."""
    text = _BODY_PART.sub(" ", _ALTERNATIVE.sub(" ", name))
    return {gear_id for gear_id, pattern in _RULES if pattern.search(text)}
