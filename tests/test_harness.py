import json

from homeset.checks import HANDOFF_SENTENCE, SAFETY_LINE
from homeset.harness import (
    BUDGET_MESSAGE,
    ERROR_MESSAGE,
    MAX_TOOL_CALLS,
    RequestState,
    extract_minutes,
    handle_request,
    make_tools,
)
from homeset.mock_wger import mock_search

GOOD_PLAN = "\n".join(
    [
        "HomeSet plan: 3 min, dumbbells, chest",
        "1. Fly With Dumbbells (item 3): 3 sets x 10 reps, rest 30 s",
        "Total time: 3.0 min (calculated)",
        SAFETY_LINE,
    ]
)


def test_extract_minutes():
    assert extract_minutes("I have 20 minutes and a mat") == 20
    assert extract_minutes("about 45 min, no equipment") == 45
    assert extract_minutes("I have an hour") == 60
    assert extract_minutes("half an hour on the mat") == 30
    assert extract_minutes("1.5 hours") == 90
    assert extract_minutes("Give me a 20-minute workout") == 20  # found by the draft test requests
    assert extract_minutes("a 1-hour session") == 60
    assert extract_minutes("work on legs") is None


def prime(state):
    """Run the search tool once so the state knows which exercises were returned."""
    search_tool, _ = make_tools(state, mock_search)
    search_tool("chest", ["dumbbells"])


def test_good_plan_passes_through():
    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    prime(state)
    outcome = handle_request(state.user_message, lambda text: GOOD_PLAN, state)
    assert outcome.kind == "plan" and outcome.failures == []


def test_handoff_skips_the_output_checks():
    state = RequestState("My knee hurts.")
    outcome = handle_request(state.user_message, lambda text: HANDOFF_SENTENCE, state)
    assert outcome.kind == "handoff" and outcome.text == HANDOFF_SENTENCE


def test_question_goes_straight_to_the_user():
    state = RequestState("Legs please.")
    outcome = handle_request(state.user_message, lambda text: "How many minutes do you have?", state)
    assert outcome.kind == "question"


def test_failed_plan_is_regenerated_once_then_passes():
    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    prime(state)
    answers = iter(["not a plan at all", GOOD_PLAN])
    prompts = []

    def ask(text):
        prompts.append(text)
        return next(answers)

    outcome = handle_request(state.user_message, ask, state)
    assert outcome.kind == "plan"
    assert len(prompts) == 2 and "failed these checks" in prompts[1]


def test_two_failures_show_a_visible_error_and_no_plan():
    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    prime(state)
    outcome = handle_request(state.user_message, lambda text: "still not a plan", state)
    assert outcome.kind == "error" and outcome.text == ERROR_MESSAGE and outcome.failures


def test_tool_call_cap_is_ten():
    state = RequestState("I have 20 minutes.")
    _, time_tool = make_tools(state)
    results = [json.loads(time_tool([{"sets": 1, "reps": 10, "rest_seconds": 0}])) for _ in range(MAX_TOOL_CALLS + 1)]
    assert "total_minutes" in results[MAX_TOOL_CALLS - 1]
    assert results[MAX_TOOL_CALLS]["error"] == "tool_call_limit"
    assert state.budget_exceeded


def test_budget_exceeded_ends_the_request_with_an_error():
    state = RequestState("I have 20 minutes.")
    state.budget_exceeded = True
    outcome = handle_request(state.user_message, lambda text: GOOD_PLAN, state)
    assert outcome.kind == "error" and outcome.text == BUDGET_MESSAGE


def test_unknown_label_and_wger_failure_come_back_as_tool_errors_not_crashes():
    state = RequestState("I have 20 minutes.")
    search_tool, _ = make_tools(state, mock_search)
    assert json.loads(search_tool("wrists", []))["error"] == "unknown_label"

    from homeset.wger import WgerUnavailable

    def broken(focus, equipment):
        raise WgerUnavailable("HTTP 429")

    search_tool, _ = make_tools(state, broken)
    reply = json.loads(search_tool("chest", []))
    assert reply["error"] == "wger_unavailable" and "I could not reach the exercise database" in reply["message"]


def test_a_plan_wrapped_in_a_question_is_checked_not_waved_through():
    # Before 2026-10-14 this reply was classed as a question and skipped every check, so an
    # exercise that never came back from wger and a missing safety line reached the user.
    reply = "\n".join(
        [
            "Sure, here is your workout.",
            "HomeSet plan: 3 min, dumbbells, chest",
            "1. Invented Move (item 3): 3 sets x 10 reps, rest 30 s",
            "Total time: 3.0 min (calculated)",
            "Shall I make it harder?",
        ]
    )
    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    prime(state)
    outcome = handle_request(state.user_message, lambda text: reply, state)
    assert outcome.kind == "error" and outcome.text == ERROR_MESSAGE
    assert outcome.failures  # the checks ran and said why


def test_tool_failures_are_recorded_on_the_outcome_with_their_reason():
    from homeset.messages import UNREACHABLE
    from homeset.wger import WgerUnavailable

    def broken(focus, equipment):
        raise WgerUnavailable("HTTP 503")

    state = RequestState("I have 20 minutes and dumbbells.  Chest.")
    search_tool, _ = make_tools(state, broken)
    search_tool("chest", ["dumbbells"])
    outcome = handle_request(state.user_message, lambda text: UNREACHABLE, state)
    assert outcome.kind == "error"
    assert outcome.tool_errors == ["wger_unavailable: HTTP 503"]  # the user sees one sentence; the log keeps why


def test_tool_errors_restart_with_each_turn_of_a_conversation():
    state = RequestState("I have 20 minutes.")
    state.tool_errors.append("unknown_label")
    state.reset_for("I have 20 minutes and a mat.  Legs.")
    assert state.tool_errors == []
