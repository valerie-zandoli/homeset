"""Label tables: the words the model may use, and the wger numbers code turns them into.

Source of truth is Section 3a of the HomeSet Agent PRD.  The model picks a label from
FOCUS_LABELS and EQUIPMENT_LABELS; this module turns the label into wger filter values.
The model never sees the numbers.

Verified against https://wger.de/api/v2/muscle/, /equipment/, and /exercisecategory/
on 2026-10-13.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BODYWEIGHT_ID = 7  # "none (bodyweight exercise)"; always searched next to owned equipment


class UnknownLabel(ValueError):
    """The model (or user) gave a label that is not in the fixed lists."""


@dataclass(frozen=True)
class Focus:
    label: str
    muscle_ids: tuple[int, ...] = ()
    category_ids: tuple[int, ...] = ()


# label -> wger muscle ids (or category ids for cardio).  Never more than five muscles
# per label, so one label never costs more than five wger searches.
FOCUS_LABELS: dict[str, Focus] = {
    f.label: f
    for f in (
        Focus("legs", muscle_ids=(10, 11, 8, 7, 15)),  # Quads, Hamstrings, Glutes, Calves, Soleus
        Focus("thighs", muscle_ids=(10, 11)),  # Quads, Hamstrings
        Focus("glutes", muscle_ids=(8,)),
        Focus("calves", muscle_ids=(7, 15)),  # Calves, Soleus
        Focus("core", muscle_ids=(6, 14)),  # Abs, Obliquus externus abdominis
        Focus("chest", muscle_ids=(4,)),
        Focus("back", muscle_ids=(12, 9)),  # Lats, Trapezius
        Focus("shoulders", muscle_ids=(2,)),
        Focus("arms", muscle_ids=(1, 5, 13)),  # Biceps, Triceps, Brachialis
        Focus("upper body", muscle_ids=(4, 12, 2, 1, 5)),
        Focus("full body", muscle_ids=(4, 12, 10, 8, 6)),
        Focus("cardio", category_ids=(15,)),
    )
}

# label -> wger equipment id
EQUIPMENT_LABELS: dict[str, int] = {
    "nothing": 7,
    "mat": 4,  # "Gym mat"
    "dumbbells": 3,
    "band": 11,  # "Resistance band"
    "kettlebell": 10,
    "pull-up bar": 6,
    "bench": 8,
    "incline bench": 9,
    "barbell": 1,
    "curl bar": 2,  # "SZ-Bar"
    "exercise ball": 5,  # "Swiss Ball"
    "cable machine": 12,
    "household items": 7,  # chair, towel, backpack: no wger match, treated as bodyweight
}

# Other phrases that map to a label (the non-first phrases in the PRD 3a table).
ALIASES: dict[str, str] = {
    "lower body": "legs",
    "abs": "core",
    "stomach": "core",
    "no equipment": "nothing",
    "bodyweight": "nothing",
    "none": "nothing",
    "yoga mat": "mat",
    "weights": "dumbbells",
    "dumbbell": "dumbbells",
    "resistance band": "band",
    "bands": "band",
    "sz-bar": "curl bar",
    "stability ball": "exercise ball",
    "swiss ball": "exercise ball",
}


def _clean(text: str) -> str:
    return " ".join(text.strip().lower().split())


def normalize_focus(text: str) -> str:
    """Return the focus label for a label or alias, or raise UnknownLabel."""
    key = _clean(text)
    key = ALIASES.get(key, key)
    if key not in FOCUS_LABELS:
        raise UnknownLabel(f"unknown focus label: {text!r}")
    return key


def normalize_equipment(text: str) -> str:
    """Return the equipment label for a label or alias, or raise UnknownLabel."""
    key = _clean(text)
    key = ALIASES.get(key, key)
    if key not in EQUIPMENT_LABELS:
        raise UnknownLabel(f"unknown equipment label: {text!r}")
    return key


def focus_filters(text: str) -> Focus:
    return FOCUS_LABELS[normalize_focus(text)]


def equipment_ids(labels: list[str] | tuple[str, ...]) -> tuple[int, ...]:
    """wger equipment ids for the owned equipment, always including bodyweight (7)."""
    ids = {BODYWEIGHT_ID}
    for label in labels:
        ids.add(EQUIPMENT_LABELS[normalize_equipment(label)])
    return tuple(sorted(ids))


def focus_label_list() -> str:
    return ", ".join(FOCUS_LABELS)


def equipment_label_list() -> str:
    return ", ".join(EQUIPMENT_LABELS)
