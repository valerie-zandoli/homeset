"""The proactive health question (LaNice, 2026-10-19).

Before the first plan, code asks one fixed question about pain, injury, surgery, pregnancy, and medical
conditions, so safety does not depend on the user volunteering it.  Everything here is code;  the model is
never asked to remember it and is never called until the question is answered.

  - A request that already says "no pain" or "no injuries" skips the question.
  - A swap of a saved plan from the last SCREEN_AGE_DAYS days skips it:  that plan was screened when it was made.
  - Only a short list of exact answers ("none", "no", "no pain", ...) clears the question.  Any health word in
    the answer is handed off by the same trigger code that guards every request;  anything else gets one more
    ask and then a hand-off, so an answer that tries to talk the check away never reaches a plan.
  - The vague-symptom question ("Is that ordinary soreness or tiredness, or does it hurt?") counts as the
    health question, so a user who answered it is not asked twice.

`Screen` holds the state that has to outlive one call:  the command line and the chat page make a separate
call for the answer, so they keep one `Screen` between the question and the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .triggers import find_trigger

SCREEN_REASON = "health screen"  # Outcome.reason of the question, so a caller can tell it from other questions
SCREEN_AGE_DAYS = 7  # a saved plan older than this is screened again before a swap


@dataclass
class Screen:
    """One conversation's health-question state.  `required=False` turns the question off (tests, evals, and
    direct harness callers that opt out);  every product entry point asks."""

    required: bool = True
    cleared: bool = False  # the question was answered, or the request or the saved plan made it unnecessary
    asked: int = 0  # how many times the question has been put to the user
    held: str | None = None  # the request that is waiting for the answer

    @property
    def pending(self) -> bool:
        """True when the question has been asked and the next message is its answer."""
        return self.required and not self.cleared and self.asked > 0


_CLEAR_ANSWER = re.compile(
    r"^(?:none|no|nope|nothing|no pain|no injur(?:y|ies)|no issues?|no health (?:issues?|problems?|concerns?)"
    r"|none of (?:these|those|the above)|none at all|nothing to report|(?:i am|i'm|im) (?:fine|healthy|good)|all good|fine)$"
)
_CLEAR_REQUEST = re.compile(
    r"\b(?:no|without|free of|zero)\s+(?:known\s+)?(?:pain|injur(?:y|ies)|medical\s+(?:conditions?|issues?|problems?)"
    r"|health\s+(?:conditions?|issues?|problems?|concerns?))\b",
    re.IGNORECASE,
)


def _plain(text: str) -> str:
    text = text.lower().replace("’", "'")
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text).split())


def answer_class(text: str) -> str:
    """'clear' only for a short, exact "none"-style answer;  everything else is 'unclear'."""
    return "clear" if _CLEAR_ANSWER.match(_plain(text)) else "unclear"


def request_clears(text: str) -> bool:
    """True when the request itself says there is no pain, injury, or condition, and nothing in it says otherwise."""
    return bool(_CLEAR_REQUEST.search(text)) and find_trigger(text) is None


def recent_enough(saved_at: str, now: datetime | None = None) -> bool:
    """True when a saved plan's date (YYYY-MM-DD ...) is within SCREEN_AGE_DAYS of now;  an unreadable date is not."""
    match = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", saved_at or "")
    if not match:
        return False
    try:
        saved = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return False
    days = ((now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0) - saved).days
    return 0 <= days <= SCREEN_AGE_DAYS
