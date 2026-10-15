"""The harness: the code that runs the loop around the model.

Rules from Section 3a of the PRD ("Harness rules") and diagram v3:
  - Output checks apply to plans only.
  - A plan that fails a check goes back to the model once; if the regenerated plan also
    fails, the user sees a visible error and no plan.
  - Hand-offs, error messages, and the one clarifying question skip the checks and go
    straight to the user.
  - The loop stops when a plan passes its checks, when the hand-off fires, when the wger
    retry fails, when the minutes are missing (one question), or when a request reaches
    10 tool calls.

This module has no model or network code, so it can be tested without an API key.
The model is passed in as `ask_model(text) -> str`; the tools are plain functions that
close over a RequestState (see make_tools).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from .assumed import MARKER, mark_assumed
from .checks import HANDOFF_SENTENCE, check_plan, check_results, classify
from .triggers import find_trigger
from .labels import UnknownLabel
from .plan_time import calculate_plan_time
from .trace import Trace, clip
from .wger import WgerUnavailable, search_exercises

MAX_TOOL_CALLS = 10
MAX_REGENERATIONS = 1

# Wording is a placeholder for the pair to settle:  it must be visible and must show no plan.
ERROR_MESSAGE = "HomeSet could not produce a plan that passed its own checks, so it is not showing one.  Please try again."
BUDGET_MESSAGE = "HomeSet reached its limit of 10 tool calls for one request, so it is not showing a plan.  Please try again."


class ToolBudgetExceeded(RuntimeError):
    pass


@dataclass
class RequestState:
    """Everything the checks need to know about one request."""

    user_message: str
    requested_minutes: float | None = None
    tool_calls: int = 0
    owned_equipment_ids: set[int] = field(default_factory=set)
    known_exercises: dict[str, list[int]] = field(default_factory=dict)  # name -> equipment ids
    budget_exceeded: bool = False
    conversation_text: str = ""  # every user message so far; the "(assumed)" marker reads it
    tool_errors: list[str] = field(default_factory=list)  # fixed-wording reasons, for the run log
    trace: Trace = field(default_factory=Trace)  # step-by-step record of this request (homeset/trace.py)
    retry_fired: bool = False  # True when the one regeneration was used

    def __post_init__(self) -> None:
        if self.requested_minutes is None:
            self.requested_minutes = extract_minutes(self.user_message)
        if not self.conversation_text:
            self.conversation_text = self.user_message

    def reset_for(self, message: str) -> None:
        """Start the next turn of one conversation.  The tool budget, the exercises seen,
        and the budget flag restart; the minutes carry over when the new message names none
        (a follow-up such as "swap the first one" keeps the earlier time)."""
        self.user_message = message
        if message not in self.conversation_text:
            self.conversation_text = f"{self.conversation_text}  {message}"
        self.requested_minutes = extract_minutes(message) or self.requested_minutes
        self.tool_calls = 0
        self.owned_equipment_ids = set()
        self.known_exercises = {}
        self.budget_exceeded = False
        self.tool_errors = []
        self.trace.clear()
        self.retry_fired = False

    def spend(self) -> None:
        if self.tool_calls >= MAX_TOOL_CALLS:
            self.budget_exceeded = True
            raise ToolBudgetExceeded(f"limit of {MAX_TOOL_CALLS} tool calls reached")
        self.tool_calls += 1


@dataclass
class Outcome:
    kind: str  # 'plan' | 'handoff' | 'question' | 'error'
    text: str
    failures: list[str] = field(default_factory=list)
    reason: str = ""  # for a hand-off fired by code:  the trigger word that fired
    tool_errors: list[str] = field(default_factory=list)  # why a tool failed, whatever the model then wrote
    retry_fired: bool = False  # the one regeneration was used
    trace: list[dict] = field(default_factory=list)  # every step of the request, in order (homeset/trace.py)


_MINUTES = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:minutes?|mins?)\b", re.IGNORECASE)
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:hours?|hrs?)\b", re.IGNORECASE)


def extract_minutes(message: str) -> float | None:
    """Minutes the user asked for, read by code (not by the model), or None."""
    total = 0.0
    found = False
    for m in _MINUTES.finditer(message):
        total += float(m.group(1))
        found = True
    for m in _HOURS.finditer(message):
        total += float(m.group(1)) * 60
        found = True
    if re.search(r"\bhalf an hour\b", message, re.IGNORECASE):
        return 30.0
    if not found and re.search(r"\ban hour\b", message, re.IGNORECASE):
        return 60.0
    return total if found else None


def _search_summary(result: dict) -> dict:
    """The funnel from the rows wger returned to the exercises the model was shown, as counts."""
    groups, names, equipment = [], [], {}
    for group in result.get("groups", []):
        shown = group.get("exercises", [])
        names.extend(ex["name"] for ex in shown)
        for ex in shown:  # the tag the equipment check will read, so a name that disagrees with it is visible
            equipment[ex["name"]] = list(ex.get("equipment_ids", []))
        examined = group.get("examined", 0)
        skipped, blocked = group.get("skipped_names", 0), group.get("blocked_advanced", 0)
        groups.append(
            {
                "filter": group.get("filter"),
                "count": group.get("count"),  # wger's total for this filter
                "examined": examined,  # rows read
                "unreadable": group.get("unreadable", 0),
                "skipped_names": skipped,
                "blocked_advanced": blocked,
                # gear the user lacks, or an exercise already listed in an earlier group
                "dropped_other": max(examined - skipped - blocked - len(shown), 0),
                "shown": len(shown),
                "cut": group.get("cut", False),
                "note": group.get("note"),
            }
        )
    return {
        "focus": result.get("focus"),
        "equipment_ids": result.get("equipment_ids", []),
        "groups": groups,
        "shown_names": names,
        "shown_equipment": equipment,  # exercise name -> equipment ids, as the model and the checks see them
    }


def make_tools(state: RequestState, search_fn: Callable = search_exercises):
    """Build the two tool functions the model may call.  Both return JSON strings.

    Every call is traced:  the arguments the model sent, then either the failure reason or the
    funnel of counts and the names the model was shown (state.trace, homeset/trace.py).
    """

    def search_exercises_tool(focus: str, equipment: list[str]) -> str:
        state.trace.add(
            "tool_call", tool="search_exercises", arguments={"focus": focus, "equipment": equipment},
            calls_before=state.tool_calls,
        )
        try:
            state.spend()
        except ToolBudgetExceeded as err:
            state.tool_errors.append("tool_call_limit")
            reply = json.dumps({"error": "tool_call_limit", "message": str(err)})
            state.trace.add("tool_result", tool="search_exercises", ok=False, error="tool_call_limit", shown_chars=len(reply))
            return reply
        try:
            result = search_fn(focus, equipment)
        except UnknownLabel as err:
            state.tool_errors.append("unknown_label")
            reply = json.dumps({"error": "unknown_label", "message": str(err)})
            state.trace.add(
                "tool_result", tool="search_exercises", ok=False, error="unknown_label", message=str(err),
                shown_chars=len(reply),
            )
            return reply
        except WgerUnavailable as err:
            state.tool_errors.append(f"wger_unavailable: {err}")  # fixed wording, never response text
            reply = json.dumps({"error": "wger_unavailable", "message": f"I could not reach the exercise database ({err})"})
            state.trace.add(
                "tool_result", tool="search_exercises", ok=False, error="wger_unavailable", message=str(err),
                shown_chars=len(reply),
            )
            return reply
        state.owned_equipment_ids.update(result["equipment_ids"])
        for group in result["groups"]:
            for ex in group["exercises"]:
                state.known_exercises[ex["name"]] = ex["equipment_ids"]
        reply = json.dumps(result)
        state.trace.add("tool_result", tool="search_exercises", ok=True, shown_chars=len(reply), **_search_summary(result))
        return reply

    def calculate_plan_time_tool(exercises: list[dict]) -> str:
        state.trace.add(
            "tool_call", tool="calculate_plan_time", arguments={"exercises": exercises}, calls_before=state.tool_calls
        )
        try:
            state.spend()
        except ToolBudgetExceeded as err:
            state.tool_errors.append("tool_call_limit")
            reply = json.dumps({"error": "tool_call_limit", "message": str(err)})
            state.trace.add("tool_result", tool="calculate_plan_time", ok=False, error="tool_call_limit", shown_chars=len(reply))
            return reply
        try:
            reply = json.dumps({"total_minutes": calculate_plan_time(exercises)})
        except ValueError as err:
            state.tool_errors.append("bad_input")
            reply = json.dumps({"error": "bad_input", "message": str(err)})
            state.trace.add(
                "tool_result", tool="calculate_plan_time", ok=False, error="bad_input", message=str(err),
                shown_chars=len(reply),
            )
            return reply
        state.trace.add("tool_result", tool="calculate_plan_time", ok=True, total_minutes=json.loads(reply)["total_minutes"])
        return reply

    return search_exercises_tool, calculate_plan_time_tool


def _feedback(failures: list[str]) -> str:
    bullets = "\n".join(f"- {f}" for f in failures)
    return (
        "Your answer failed these checks:\n"
        f"{bullets}\n"
        "Write the plan again in the OUTPUT FORMAT, using only exercises from the tool results."
    )


def handle_request(user_message: str, ask_model: Callable[[str], str], state: RequestState) -> Outcome:
    """Run one request through the model, the output checks, and at most one regeneration.

    Clear safety triggers (pain, injury, surgery, pregnancy, a medical condition) are
    checked first, in code, over the whole conversation:  the exact hand-off sentence goes
    to the user and the model is never called.  The prompt's step 1 still handles the
    ambiguous cases and is the second layer behind this check.

    Every outcome carries the reasons any tool failed during the request, so a saved run
    shows why the user saw "could not reach" (HTTP 503, an unreadable response, a deadline).
    """
    outcome = _run_request(user_message, ask_model, state)
    outcome.tool_errors = list(state.tool_errors)
    outcome.retry_fired = state.retry_fired
    state.trace.add(
        "outcome", kind=outcome.kind, retry_fired=state.retry_fired, failures=list(outcome.failures),
        tool_errors=list(state.tool_errors), reason=outcome.reason, text=clip(outcome.text),
    )
    outcome.trace = state.trace.as_list()
    return outcome


def _ask(ask_model: Callable[[str], str], state: RequestState, prompt: str, attempt: int) -> str:
    """One model call, on record:  what was sent (the tool calls land between these two events)
    and what came back, with the harness's reading of its kind."""
    state.trace.add("model_call", attempt=attempt, prompt=clip(prompt))
    text = ask_model(prompt)
    state.trace.add("model_reply", attempt=attempt, kind=classify(text), text=clip(text))
    return text


def _run_request(user_message: str, ask_model: Callable[[str], str], state: RequestState) -> Outcome:
    state.trace.add("request", message=clip(user_message), minutes_requested=state.requested_minutes)
    trigger = find_trigger(state.conversation_text or user_message)
    state.trace.add("trigger", fired=trigger is not None, word=trigger)
    if trigger:  # the model is never called
        return Outcome("handoff", HANDOFF_SENTENCE, reason=trigger)
    text = _ask(ask_model, state, user_message, 0)
    for attempt in range(MAX_REGENERATIONS + 1):
        if state.budget_exceeded:
            state.trace.add("budget_exceeded", attempt=attempt)
            return Outcome("error", BUDGET_MESSAGE)
        kind = classify(text)
        if kind in ("handoff", "error", "question"):  # direct path: skip the output checks
            state.trace.add("checks", attempt=attempt, skipped=True, reason=f"direct path: {kind}")
            return Outcome(kind, text)
        marked = mark_assumed(text, state.conversation_text)  # code writes "(assumed)", not the model
        state.trace.add(
            "assumed", attempt=attempt, model_wrote_marker=MARKER in text, code_changed_line_1=marked != text
        )
        text = marked
        failures = check_plan(text, state.known_exercises, state.owned_equipment_ids, state.requested_minutes)
        state.trace.add(
            "checks", attempt=attempt, skipped=False, passed=not failures, results=check_results(failures),
            failures=list(failures),
        )
        if not failures:
            return Outcome("plan", text)
        if attempt == MAX_REGENERATIONS:
            return Outcome("error", ERROR_MESSAGE, failures)
        state.retry_fired = True
        state.trace.add("regenerate", attempt=attempt + 1, failures=list(failures))
        text = _ask(ask_model, state, _feedback(failures), attempt + 1)
    return Outcome("error", ERROR_MESSAGE)  # unreachable; keeps the type checker calm
