"""The "(assumed)" marker, written by code (README open item 8).

Rule (PRD 3b, output format):  line 1 of a plan carries "(assumed)" after any equipment or
focus the user did not give.  The model forgot the marker in about 1 of 20 runs even with a
reworded prompt, so code decides and writes it:

  - the user's words (every user message in the conversation) are matched against the label
    tables and their aliases in labels.py, plus a few extra words and spellings below;
  - any marker the model wrote is removed, and code adds one for each item the user did not
    name.

A user who names equipment or focus in a word this module does not know gets a visible,
harmless "(assumed)".  Add the word to the sets below and add a test.

This module has no model or network code.
"""

from __future__ import annotations

import re

from .labels import ALIASES, EQUIPMENT_LABELS, FOCUS_LABELS

MARKER = "(assumed)"

# Words and spellings beyond the label tables.
_EXTRA_EQUIPMENT = {
    "no equipment", "no gear", "without equipment", "no weights", "body weight", "my body",
    "dumbbell", "dumbell", "dumbells", "dumb bell", "dumb bells", "kettle bell", "pullup bar",
    "pull up bar", "chin up bar", "bands", "resistance bands", "exercise mat", "gym mat",
    "ball", "chair", "towel", "backpack", "couch", "sofa", "water bottle", "bottle", "books",
}
_EXTRA_FOCUS = {
    "leg", "glute", "butt", "thigh", "arm", "shoulder", "calf", "quads", "quad", "hamstring",
    "hamstrings", "biceps", "triceps", "lats", "traps", "delts", "pecs", "obliques", "hips",
    "whole body", "total body", "tummy", "belly",
}

# "back" the body part versus "back" the adverb ("I am back from a break").
_BACK_ADVERB = re.compile(
    r"\bback (?:from|to|in|at|after|on|into|again)\b"
    r"|\b(?:come|coming|came|get|getting|got|going|go|went|am|be|been|is|are|i'm|im) back\b"
)

_LINE1 = re.compile(r"^(HomeSet plan: \d+(?:\.\d+)? min, )(.+), (.+)$")


def _norm(text: str) -> str:
    t = text.lower().replace("-", " ").replace("’", "'")
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", t).split())


def _terms(labels, alias_targets) -> set[str]:
    found = {_norm(label) for label in labels}
    found |= {_norm(alias) for alias, target in ALIASES.items() if target in alias_targets}
    return found


_EQUIPMENT_TERMS = _terms(EQUIPMENT_LABELS, EQUIPMENT_LABELS) | {_norm(w) for w in _EXTRA_EQUIPMENT}
_FOCUS_TERMS = _terms(FOCUS_LABELS, FOCUS_LABELS) | {_norm(w) for w in _EXTRA_FOCUS}
# "none" and "nothing" are equipment answers; "back" is handled by _BACK_ADVERB.


def _mentions(text: str, terms: set[str]) -> bool:
    padded = f" {text} "
    return any(f" {term} " in padded for term in terms)


def equipment_stated(user_text: str) -> bool:
    """True when the user named equipment, or said they have none."""
    return _mentions(_norm(user_text), _EQUIPMENT_TERMS)


def focus_stated(user_text: str) -> bool:
    """True when the user named a focus area."""
    cleaned = _BACK_ADVERB.sub(" ", _norm(user_text))
    return _mentions(" ".join(cleaned.split()), _FOCUS_TERMS)


def _strip_marker(field: str) -> str:
    return re.sub(r"\s*\(assumed\)", "", field).strip()


def mark_assumed(plan_text: str, user_text: str) -> str:
    """Return the plan with "(assumed)" on line 1 exactly where the user named nothing.

    Text that is not a plan (line 1 is not "HomeSet plan: <n> min, <equipment>, <focus>")
    comes back unchanged, so the format check still sees what the model wrote.
    """
    lines = plan_text.split("\n")
    index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if index is None:
        return plan_text
    match = _LINE1.match(lines[index].strip())
    if not match:
        return plan_text
    prefix, equipment, focus = match.groups()
    equipment, focus = _strip_marker(equipment), _strip_marker(focus)
    if not equipment_stated(user_text):
        equipment = f"{equipment} {MARKER}"
    if not focus_stated(user_text):
        focus = f"{focus} {MARKER}"
    lines[index] = f"{prefix}{equipment}, {focus}"
    return "\n".join(lines)
