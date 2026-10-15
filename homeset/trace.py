"""A step-by-step trace of one request.

The trace is the evidence for telling model reasoning from harness behavior:  what the model
was asked, which tool it called with which arguments, what came back and what the model was
shown, which output check failed, and whether the one regeneration fired.  Saved runs keep the
final text only, so before this module a miss could be inferred but not read.

This module has no model or network code.  Recording never changes an outcome:  an event is
plain data appended to a list.  Long text is clipped so a run file stays readable.
"""

from __future__ import annotations

import copy

MAX_TEXT_CHARS = 4000


def clip(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Text cut to `limit` characters, with a visible marker when something was cut."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [clipped, {len(text) - limit} more characters]"


class Trace:
    """An ordered list of events.  Each event has a step number, a name, and plain data."""

    def __init__(self) -> None:
        self._events: list[dict] = []

    def add(self, event: str, **data) -> None:
        # Copy the data so a list the caller changes later cannot rewrite the record.
        self._events.append({"step": len(self._events) + 1, "event": event, **copy.deepcopy(data)})

    def clear(self) -> None:
        self._events = []

    def as_list(self) -> list[dict]:
        return copy.deepcopy(self._events)

    def __len__(self) -> int:
        return len(self._events)


def trace_fields(outcome) -> dict:
    """The two fields every saved run row carries beside the final text and the checks."""
    return {"retry_fired": outcome.retry_fired, "trace": outcome.trace}
