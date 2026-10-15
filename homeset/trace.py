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
import json

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


def _short(text, limit: int = 100) -> str:
    one_line = " ".join(str(text).split())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def _funnel_lines(event: dict) -> list[str]:
    lines = []
    for g in event.get("groups", []):
        line = (
            f"{g['filter']}: wger count {g['count']}, examined {g['examined']}, skipped {g['skipped_names']}, "
            f"blocked {g['blocked_advanced']}, other {g['dropped_other']}, shown {g['shown']}"
        )
        lines.append(line + (f"  ({g['note']})" if g.get("note") else ""))
    return lines


def _body(e: dict) -> str:
    kind = e["event"]
    if kind == "request":
        return f"{_short(e['message'])}  (minutes requested: {e.get('minutes_requested')})"
    if kind == "trigger":
        return f"fired on {e['word']!r}; the model is not called" if e["fired"] else "not fired"
    if kind == "model_call":
        return f"attempt {e['attempt']}: {_short(e['prompt'])}"
    if kind == "model_reply":
        return f"attempt {e['attempt']}, read as {e['kind']}: {_short(e['text'])}"
    if kind == "tool_call":
        args = ", ".join(f"{k}={v!r}" for k, v in e["arguments"].items())
        return f"{e['tool']}({_short(args, 110)})  [calls before: {e['calls_before']}]"
    if kind == "tool_result":
        if not e["ok"]:
            detail = f" ({_short(e['message'])})" if e.get("message") else ""
            return f"{e['tool']} FAILED: {e['error']}{detail}"
        if e["tool"] == "search_exercises":
            head = f"ok; {len(e['shown_names'])} names shown to the model, {e['shown_chars']} characters"
            return "\n".join([head] + ["      " + line for line in _funnel_lines(e)])
        return f"ok; total {e['total_minutes']} min"
    if kind == "assumed":
        wrote = "yes" if e["model_wrote_marker"] else "no"
        changed = "yes" if e["code_changed_line_1"] else "no"
        return f"attempt {e['attempt']}: model wrote the marker: {wrote}; code changed line 1: {changed}"
    if kind == "checks":
        if e.get("skipped"):
            return f"attempt {e['attempt']}: skipped ({e['reason']})"
        if e["passed"]:
            return f"attempt {e['attempt']}: PASS"
        failed = [name for name, ok in e["results"].items() if ok is False]
        return f"attempt {e['attempt']}: FAIL ({', '.join(failed)})\n" + "\n".join(
            "      " + _short(f) for f in e["failures"]
        )
    if kind == "regenerate":
        return f"attempt {e['attempt']}: sent back to the model for {len(e['failures'])} failure(s)"
    if kind == "budget_exceeded":
        return f"attempt {e['attempt']}: the tool-call cap was reached"
    if kind == "outcome":
        retry = "yes" if e["retry_fired"] else "no"
        extra = f"; tool errors: {', '.join(e['tool_errors'])}" if e.get("tool_errors") else ""
        return f"{e['kind']}; retry fired: {retry}{extra}"
    rest = {k: v for k, v in e.items() if k not in ("step", "event")}
    return _short(json.dumps(rest))


def format_trace(events: list[dict]) -> str:
    """A trace as one readable line per step (the saved file keeps the full text)."""
    return "\n".join(f"{e['step']:>2}  {e['event']:<13}{_body(e)}" for e in events)
