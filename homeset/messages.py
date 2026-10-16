"""Fixed wording for every message the agent writes when it does not give a plan.

DRAFT (2026-10-13), for Valerie and Yadan to agree.  The PRD (Section 3b) still has the
looser v0 wording for the "no exercises" and "too few exercises" cases; update the PRD
only after both of you agree.

Why fixed wording:  the harness sends these messages straight to the user without the
plan checks, so it must recognize them.  A fixed opening sentence makes that a string
match instead of a guess.  The <slots> are filled in by the model.

Kinds the harness assigns (see checks.classify):
  handoff   the exact HANDOFF sentence
  error     starts with "I could not reach the exercise database"
  question  anything else that does not start with "HomeSet plan:" and ends with "?"
"""

from __future__ import annotations

MIN_MINUTES = 10  # PRD 1b:  primary users have 10 to 45 minutes at a time
MAX_MINUTES = 45

HANDOFF = (
    "I cannot plan workouts around pain, injuries, or medical conditions.  "
    "Please talk to a doctor or physical therapist first."
)
VAGUE_QUESTION = "Is that ordinary soreness or tiredness, or does it hurt?"  # fired by code (triggers.find_vague)
UNREACHABLE = "I could not reach the exercise database.  Would you like me to try once more?"
NO_MATCH = (
    "I could not find any exercises for <focus> with <equipment>.  "
    "Would you like to try a different focus or add equipment?"
)
TOO_FEW = (
    "I found only <n> exercises for <focus> with <equipment>, which is not enough for <minutes> minutes.  "
    "Would you like a shorter workout of about <shorter> minutes?"
)
OUT_OF_RANGE = (
    f"I plan workouts of {MIN_MINUTES} to {MAX_MINUTES} minutes, and <n> minutes is outside that range.  "
    f"How many minutes do you have, between {MIN_MINUTES} and {MAX_MINUTES}?"
)
MISSING_MINUTES = "How many minutes do you have?"
UNKNOWN_LABEL = "I am not sure which <focus or equipment> you mean.  Which of these fits best: <the closest labels>?"

# Opening words used to recognize each message (whitespace-normalized, case-insensitive).
PREFIXES = {
    "error": ("I could not reach the exercise database",),
    "question": (
        "I could not find any exercises for",
        "I found only",
        "I plan workouts of",
        "How many minutes do you have",
        "I am not sure which",
    ),
}
