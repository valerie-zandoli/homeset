"""Rep cap on kettlebell moves (README Open item 10).

Yadan proposed on 2026-10-15 that kettlebell moves get a cap on reps per set, and gave the
number in Slack:  8, which matches the beginner tie-breaker "a first-time exerciser can do 8
clean reps unassisted" (PRD 3d, rule C).  The grading of request set A found 3x8 on a
kettlebell move (a04), so no plan had gone over 8 yet; this makes the limit a guarantee
rather than a habit of the model.

A kettlebell move is an exercise that wger tags with kettlebell equipment (id 10), or whose
name names a kettlebell (gear.py reads the name, because wger's tag can disagree with it).
The cap is per set:  "3 sets x 8 reps" passes and "3 sets x 10 reps" fails.

The check runs in checks.py as a backstop that feeds the normal retry; it never edits a plan.
The prompt (step 6) states the same number, filled in from this module so the two cannot drift.

This module has no model or network code.
"""

from __future__ import annotations

from collections.abc import Iterable

from .gear import gear_ids_from_name

KETTLEBELL_MAX_REPS = 8  # reps per set, decided by Yadan 2026-10-15
KETTLEBELL_ID = 10  # labels.EQUIPMENT_LABELS["kettlebell"]


def is_kettlebell_move(name: str, equipment_ids: Iterable[int] = ()) -> bool:
    """True when wger tags the exercise with a kettlebell or its name names one."""
    return KETTLEBELL_ID in set(equipment_ids) or KETTLEBELL_ID in gear_ids_from_name(name)


def over_rep_cap(name: str, reps: int, equipment_ids: Iterable[int] = ()) -> bool:
    """True when this is a kettlebell move with more than the allowed reps per set."""
    return reps > KETTLEBELL_MAX_REPS and is_kettlebell_move(name, equipment_ids)
