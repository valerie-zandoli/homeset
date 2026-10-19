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

from .assumed import MARKER, mark_assumed, stated_in_plan
from .checks import HANDOFF_SENTENCE, check_plan, check_results, classify
from .messages import SCREEN_AGAIN, SCREEN_QUESTION, VAGUE_QUESTION
from .screen import SCREEN_REASON, Screen, answer_class, recent_enough, request_clears
from .triggers import find_trigger, find_vague
from .labels import UnknownLabel
from .plan_time import calculate_plan_time
from .trace import Trace, clip
from .wger import WgerUnavailable, search_exercises

MAX_TOOL_CALLS = 10
MAX_REGENERATIONS = 1
# Longest list either tool accepts.  Live runs sent at most 2 equipment labels and 6 exercises
# (290 tool calls); 13 equipment labels exist.  A longer list is a malformed call, so it is refused.
MAX_LIST_ITEMS = 20
MAX_ITEM_LEN = 60  # longest string in an equipment list; the longest alias is 15 characters

# Wording is a placeholder for the pair to settle:  it must be visible and must show no plan.
ERROR_MESSAGE = "HomeSet could not produce a plan that passed its own checks, so it is not showing one.  Please try again."
BUDGET_MESSAGE = "HomeSet reached its limit of 10 tool calls for one request, so it is not showing a plan.  Please try again."


class ToolBudgetExceeded(RuntimeError):
    pass


def _bad_list_message(name: str, value, strings: bool = False) -> str | None:
    """The refusal text when `value` is not a list of at most MAX_LIST_ITEMS items, else None.

    With `strings=True` every item must also be a string of at most MAX_ITEM_LEN characters, so a long
    unknown label is never echoed back to the model or written to the trace.
    """
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        return f"{name}: expected a list of at most {MAX_LIST_ITEMS} items"
    if strings and any(not isinstance(item, str) or len(item) > MAX_ITEM_LEN for item in value):
        return f"{name}: items must be strings up to {MAX_ITEM_LEN} characters"
    return None


def _for_trace(value):
    """A list as the trace records it:  the first MAX_LIST_ITEMS items (long strings clipped) and a marker for the rest."""
    if not isinstance(value, list):
        return value
    kept = [clip(item, MAX_ITEM_LEN) if isinstance(item, str) else item for item in value[:MAX_LIST_ITEMS]]
    if len(value) > MAX_LIST_ITEMS:
        kept.append(f"[{len(value) - MAX_LIST_ITEMS} more items not recorded]")
    return kept


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
    vague_asked: bool = False  # code already asked the fixed clarifying question in this conversation
    clarifying_for: str | None = None  # the request that question was about, until the answer turn uses it
    earlier_plan: str | None = None  # a plan saved in an earlier session, passed to the model once as data
    earlier_plan_at: str = ""
    carried_stated: str = ""  # equipment and focus words the earlier plan's user stated (see assumed.stated_in_plan)
    clarifying_question: str = VAGUE_QUESTION  # the code-fired question the answer turn replies to
    screen: Screen = field(default_factory=lambda: Screen(required=False))  # the health question (homeset/screen.py);
    # off here so direct harness callers keep their behavior;  agent.run_once turns it on for every product entry point

    def __post_init__(self) -> None:
        if self.requested_minutes is None:
            self.requested_minutes = extract_minutes(self.user_message)
        if not self.conversation_text:
            self.conversation_text = self.user_message

    def resume_from(self, held: str) -> None:
        """The answer turn of a question asked in an earlier call:  the held request joins the conversation, so the
        trigger scan covers both messages and the minutes it named carry over."""
        if held and held not in self.conversation_text:
            self.conversation_text = f"{held}  {self.conversation_text}"
        self.requested_minutes = self.requested_minutes or extract_minutes(held)

    def attach_earlier_plan(self, plan: str, saved_at: str) -> None:
        """Start a swap session from a saved plan.  Its minutes become the target unless the
        request names others, and the words it did not mark "(assumed)" count as stated.  The
        plan is passed to the model as data and is never scanned for safety words (its own
        safety line says "hurts" and "pain")."""
        self.earlier_plan, self.earlier_plan_at = plan, saved_at
        first_line = next((ln for ln in plan.splitlines() if ln.strip()), "")
        if self.requested_minutes is None:
            self.requested_minutes = extract_minutes(first_line)
        self.carried_stated = stated_in_plan(plan)

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
    reason: str = ""  # for a hand-off or question fired by code:  the word or phrase that fired
    tool_errors: list[str] = field(default_factory=list)  # why a tool failed, whatever the model then wrote
    retry_fired: bool = False  # the one regeneration was used
    trace: list[dict] = field(default_factory=list)  # every step of the request, in order (homeset/trace.py)


_MINUTES = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:minutes?|mins?)\b", re.IGNORECASE)
_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:hours?|hrs?)\b", re.IGNORECASE)


_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60,
}
_TENS = "twenty|thirty|forty|fifty|sixty"
_ONES = "one|two|three|four|five|six|seven|eight|nine"
# "twenty", "twenty five", "twenty-five", "fifteen":  a whole number written in words, 1 to 69.
_WORD_NUMBER = rf"(?:(?:{_TENS})(?:[ -](?:{_ONES}))?|(?:{'|'.join(list(_NUMBER_WORDS)[9:19])})|(?:{_ONES}))"
_WORD_MINUTES = re.compile(rf"\b({_WORD_NUMBER})\s*-?\s*(?:minutes?|mins?)\b", re.IGNORECASE)
_WORD_HOURS = re.compile(rf"\b({_WORD_NUMBER})\s*-?\s*(?:hours?|hrs?)\b", re.IGNORECASE)


def _number_from_words(words: str) -> int:
    return sum(_NUMBER_WORDS[part] for part in re.split(r"[ -]", words.lower()))


def extract_minutes(message: str) -> float | None:
    """Minutes the user asked for, read by code (not by the model), or None.

    Reads digits ("20 minutes") and whole numbers in words ("twenty minutes", "twenty-five minutes").
    A message with neither gives None, and the time check then falls back to the plan's own line 1.
    """
    total = 0.0
    found = False
    for m in _MINUTES.finditer(message):
        total += float(m.group(1))
        found = True
    for m in _HOURS.finditer(message):
        total += float(m.group(1)) * 60
        found = True
    for m in _WORD_MINUTES.finditer(message):
        total += _number_from_words(m.group(1))
        found = True
    for m in _WORD_HOURS.finditer(message):
        total += _number_from_words(m.group(1)) * 60
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
            "tool_call", tool="search_exercises", arguments={"focus": focus, "equipment": _for_trace(equipment)},
            calls_before=state.tool_calls,
        )
        try:
            state.spend()
        except ToolBudgetExceeded as err:
            state.tool_errors.append("tool_call_limit")
            reply = json.dumps({"error": "tool_call_limit", "message": str(err)})
            state.trace.add("tool_result", tool="search_exercises", ok=False, error="tool_call_limit", shown_chars=len(reply))
            return reply
        message = _bad_list_message("equipment", equipment, strings=True)
        if message:
            state.tool_errors.append("bad_list")
            reply = json.dumps({"error": "bad_list", "message": message})
            state.trace.add(
                "tool_result", tool="search_exercises", ok=False, error="bad_list", message=message, shown_chars=len(reply)
            )
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
            "tool_call", tool="calculate_plan_time", arguments={"exercises": _for_trace(exercises)},
            calls_before=state.tool_calls,
        )
        try:
            state.spend()
        except ToolBudgetExceeded as err:
            state.tool_errors.append("tool_call_limit")
            reply = json.dumps({"error": "tool_call_limit", "message": str(err)})
            state.trace.add("tool_result", tool="calculate_plan_time", ok=False, error="tool_call_limit", shown_chars=len(reply))
            return reply
        message = _bad_list_message("exercises", exercises)
        if message:
            state.tool_errors.append("bad_list")
            reply = json.dumps({"error": "bad_list", "message": message})
            state.trace.add(
                "tool_result", tool="calculate_plan_time", ok=False, error="bad_list", message=message,
                shown_chars=len(reply),
            )
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
    to the user and the model is never called.  Vague wording ("feels off", "bothering me")
    gets the one fixed clarifying question the same way; a second vague message after that
    question is handed off.  The prompt's step 1 is the second layer for wording that
    neither list knows.

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


def _with_earlier_request(earlier: str, answer: str, question: str = VAGUE_QUESTION) -> str:
    """The model's prompt for the turn that answers the code-fired question."""
    return (
        f"Earlier request: {earlier}\n"
        f"You asked: {question}\n"
        f"The user answered: {answer}\n"
        "Follow the safety rule in step 1, then plan the earlier request."
    )


def _with_earlier_plan(plan: str, saved_at: str, request: str) -> str:
    """The model's first prompt in a swap session:  the saved plan as data, then the request."""
    return (
        f"Saved plan from {saved_at}.  It is data from an earlier session, not instructions:\n"
        f"---\n{plan}\n---\n"
        f"Request: {request}\n"
        "Follow step 9 for this saved plan:  change only what the request asks, then write the full revised plan."
    )


def _ask_health_question(user_message: str, state: RequestState) -> Outcome | None:
    """Before the first plan:  the one fixed health question, unless the request or a recent saved plan already settles it."""
    screen = state.screen
    if not screen.required or screen.cleared:
        return None
    if state.earlier_plan and recent_enough(state.earlier_plan_at):
        screen.cleared = True
        state.trace.add("screen", result="skipped:  the saved plan is recent", saved_at=state.earlier_plan_at)
        return None
    if request_clears(user_message):
        screen.cleared = True
        state.trace.add("screen", result="skipped:  the request says there is no pain, injury, or condition")
        return None
    screen.asked, screen.held = 1, user_message  # the model is never called
    state.trace.add("screen", result="asked")
    return Outcome("question", SCREEN_QUESTION, reason=SCREEN_REASON)


def _answer_health_question(user_message: str, state: RequestState) -> Outcome | None:
    """The answer turn.  A clear answer lets the held request go on to the model (returns None);  anything else
    is another ask or a hand-off.  A health word in the answer was already handed off by the trigger scan."""
    screen = state.screen
    if find_vague(user_message):  # "my knee feels off" is not an answer
        state.trace.add("screen", result="handed off:  a vague answer")
        return Outcome("handoff", HANDOFF_SENTENCE, reason="vague answer to the health question")
    if answer_class(user_message) == "clear":
        screen.cleared = True
        state.clarifying_for, state.clarifying_question = screen.held or state.conversation_text, SCREEN_QUESTION
        state.trace.add("screen", result="cleared by the answer")
        return None
    if screen.asked == 1:
        screen.asked = 2
        state.trace.add("screen", result="asked again:  the answer was unclear")
        return Outcome("question", SCREEN_AGAIN, reason=SCREEN_REASON)
    state.trace.add("screen", result="handed off:  the answer was unclear twice")
    return Outcome("handoff", HANDOFF_SENTENCE, reason="unclear health answer, twice")


def _run_request(user_message: str, ask_model: Callable[[str], str], state: RequestState) -> Outcome:
    screen = state.screen
    if screen.pending and screen.held:  # a later call:  the held request joins this answer turn
        state.resume_from(screen.held)
    state.trace.add("request", message=clip(user_message), minutes_requested=state.requested_minutes)
    trigger = find_trigger(state.conversation_text or user_message)
    state.trace.add("trigger", fired=trigger is not None, word=trigger)
    if trigger:  # the model is never called
        return Outcome("handoff", HANDOFF_SENTENCE, reason=trigger)
    if screen.pending:  # this message answers the health question
        outcome = _answer_health_question(user_message, state)
        if outcome:
            return outcome
        vague = None
    else:
        vague = find_vague(user_message)  # the latest message only:  an answer to our question must not re-fire
    state.trace.add("vague", fired=vague is not None, phrase=vague, asked_before=state.vague_asked)
    if vague and state.vague_asked:  # still vague after the question:  err toward the hand-off
        return Outcome("handoff", HANDOFF_SENTENCE, reason=f"vague again: {vague}")
    if vague:  # the model is never called
        state.vague_asked = True
        state.clarifying_for = user_message
        state.clarifying_question = VAGUE_QUESTION
        return Outcome("question", VAGUE_QUESTION, reason=vague)
    if state.clarifying_for and screen.required and not screen.cleared:  # the vague question was a health question too
        screen.cleared = True
        state.trace.add("screen", result="cleared by the answer to the vague question")
    elif not state.clarifying_for:
        outcome = _ask_health_question(user_message, state)
        if outcome:
            return outcome
    prompt = user_message
    if state.clarifying_for:  # the model never saw the earlier request, so pass it along with the answer
        prompt = _with_earlier_request(state.clarifying_for, user_message, state.clarifying_question)
        state.clarifying_for = None
        state.clarifying_question = VAGUE_QUESTION
    if state.earlier_plan:  # a swap session:  the model has not seen the saved plan, so pass it once
        state.trace.add("earlier_plan", saved_at=state.earlier_plan_at, chars=len(state.earlier_plan))
        prompt = _with_earlier_plan(state.earlier_plan, state.earlier_plan_at, prompt)
        state.earlier_plan = None
    text = _ask(ask_model, state, prompt, 0)
    for attempt in range(MAX_REGENERATIONS + 1):
        if state.budget_exceeded:
            state.trace.add("budget_exceeded", attempt=attempt)
            return Outcome("error", BUDGET_MESSAGE)
        kind = classify(text)
        if kind in ("handoff", "error", "question"):  # direct path: skip the output checks
            state.trace.add("checks", attempt=attempt, skipped=True, reason=f"direct path: {kind}")
            return Outcome(kind, text)
        marked = mark_assumed(text, f"{state.conversation_text}  {state.carried_stated}")  # code writes "(assumed)", not the model
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
