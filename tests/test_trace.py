"""The trace of a request, tested with no model and no network."""

import json

from homeset.checks import HANDOFF_SENTENCE
from homeset.harness import MAX_TOOL_CALLS, RequestState, handle_request, make_tools
from homeset.mock_wger import mock_search
from homeset.trace import MAX_TEXT_CHARS, Trace, clip


def test_events_are_numbered_in_order():
    trace = Trace()
    trace.add("tool_call", tool="search_exercises")
    trace.add("tool_result", ok=True)
    events = trace.as_list()
    assert [e["step"] for e in events] == [1, 2]
    assert [e["event"] for e in events] == ["tool_call", "tool_result"]
    assert len(trace) == 2


def test_clip_keeps_short_text_and_marks_a_cut():
    assert clip("short") == "short"
    cut = clip("x" * (MAX_TEXT_CHARS + 25))
    assert cut.startswith("x" * MAX_TEXT_CHARS) and "25 more characters" in cut


def test_recorded_data_is_a_copy():
    arguments = {"equipment": ["mat"]}
    trace = Trace()
    trace.add("tool_call", arguments=arguments)
    arguments["equipment"].append("dumbbells")  # a later change must not rewrite the record
    assert trace.as_list()[0]["arguments"] == {"equipment": ["mat"]}


def test_reset_for_starts_a_new_trace_and_clears_the_retry_flag():
    state = RequestState("I have 20 minutes and a mat.  Legs.")
    state.trace.add("tool_call", tool="search_exercises")
    state.retry_fired = True
    state.reset_for("Swap the first exercise.")
    assert len(state.trace) == 0 and state.retry_fired is False


def test_outcome_carries_a_copy_of_the_trace_and_the_retry_flag():
    state = RequestState("My knee hurts.")
    state.trace.add("note", detail="kept")
    outcome = handle_request(state.user_message, lambda text: HANDOFF_SENTENCE, state)
    assert outcome.trace[0]["event"] == "note"
    assert outcome.retry_fired is False
    state.trace.clear()
    assert outcome.trace  # clearing the state later leaves the outcome's record alone


# --- tool calls and results ---------------------------------------------------------------


def events_named(state, name):
    return [e for e in state.trace.as_list() if e["event"] == name]


def test_a_search_records_the_arguments_and_the_funnel_of_counts():
    state = RequestState("I have 20 minutes and dumbbells.  Chest.")
    search_tool, _ = make_tools(state, mock_search)
    search_tool("chest", ["dumbbells"])
    call, = events_named(state, "tool_call")
    result, = events_named(state, "tool_result")
    assert call["tool"] == "search_exercises"
    assert call["arguments"] == {"focus": "chest", "equipment": ["dumbbells"]}
    assert call["calls_before"] == 0
    assert result["ok"] is True and result["shown_chars"] > 0
    for group in result["groups"]:  # every row read is either dropped for a reason or shown
        assert group["examined"] == group["skipped_names"] + group["blocked_advanced"] + group["dropped_other"] + group["shown"]
    assert sorted(result["shown_names"]) == sorted(state.known_exercises)


def test_the_funnel_names_why_rows_did_not_reach_the_model():
    def stub(focus, equipment):
        exercises = [{"id": i, "name": f"Move {i}", "equipment_ids": [7]} for i in range(3)]
        group = {"filter": "muscles=4", "count": 40, "examined": 10, "cut": True, "note": "showing 10 of 40",
                 "skipped_names": 2, "unreadable": 1, "blocked_advanced": 1, "exercises": exercises}
        return {"focus": "chest", "equipment_ids": [7], "groups": [group]}

    state = RequestState("I have 20 minutes.  Chest.")
    search_tool, _ = make_tools(state, stub)
    search_tool("chest", [])
    result, = events_named(state, "tool_result")
    group, = result["groups"]
    assert (group["count"], group["examined"], group["skipped_names"], group["blocked_advanced"]) == (40, 10, 2, 1)
    assert group["dropped_other"] == 4 and group["shown"] == 3  # 10 - 2 - 1 - 3
    assert group["cut"] is True and group["note"] == "showing 10 of 40"


def test_a_failed_search_records_the_reason_and_what_the_model_was_told():
    from homeset.wger import WgerUnavailable

    def broken(focus, equipment):
        raise WgerUnavailable("HTTP 503")

    state = RequestState("I have 20 minutes.")
    search_tool, _ = make_tools(state, broken)
    search_tool("chest", [])
    result, = events_named(state, "tool_result")
    assert result["ok"] is False and result["error"] == "wger_unavailable" and result["message"] == "HTTP 503"
    assert state.tool_errors == ["wger_unavailable: HTTP 503"]  # the same reason the run log keeps


def test_an_unknown_label_is_recorded():
    state = RequestState("I have 20 minutes.")
    search_tool, _ = make_tools(state, mock_search)
    search_tool("wrists", [])
    result, = events_named(state, "tool_result")
    assert result["ok"] is False and result["error"] == "unknown_label" and result["message"]


def test_the_tool_call_cap_is_visible_in_the_trace():
    state = RequestState("I have 20 minutes.")
    _, time_tool = make_tools(state)
    for _ in range(MAX_TOOL_CALLS + 1):
        time_tool([{"sets": 1, "reps": 10, "rest_seconds": 0}])
    results = events_named(state, "tool_result")
    calls = events_named(state, "tool_call")
    assert len(results) == len(calls) == MAX_TOOL_CALLS + 1
    assert results[MAX_TOOL_CALLS - 1]["ok"] is True
    assert results[MAX_TOOL_CALLS]["ok"] is False and results[MAX_TOOL_CALLS]["error"] == "tool_call_limit"
    assert calls[MAX_TOOL_CALLS]["calls_before"] == MAX_TOOL_CALLS  # the refused call is still on record


def test_the_time_tool_records_its_input_and_total():
    state = RequestState("I have 20 minutes.")
    _, time_tool = make_tools(state)
    exercises = [{"sets": 3, "reps": 10, "rest_seconds": 30}]
    reply = json.loads(time_tool(exercises))
    call, = events_named(state, "tool_call")
    result, = events_named(state, "tool_result")
    assert call["arguments"] == {"exercises": exercises}
    assert result["ok"] is True and result["total_minutes"] == reply["total_minutes"]


def test_bad_time_input_is_recorded_as_a_failure():
    state = RequestState("I have 20 minutes.")
    _, time_tool = make_tools(state)
    time_tool([{"sets": "many", "reps": 10, "rest_seconds": 30}])
    result, = events_named(state, "tool_result")
    assert result["ok"] is False and result["error"] == "bad_input"


# --- the request path ---------------------------------------------------------------------

from homeset.agent import run_conversation  # noqa: E402
from homeset.checks import CHECK_NAMES, SAFETY_LINE, check_results  # noqa: E402
from homeset.harness import BUDGET_MESSAGE, ERROR_MESSAGE  # noqa: E402

GOOD_PLAN = "\n".join(
    [
        "HomeSet plan: 3 min, dumbbells, chest",
        "1. Fly With Dumbbells (item 3): 3 sets x 10 reps, rest 30 s",
        "Total time: 3.0 min (calculated)",
        SAFETY_LINE,
    ]
)


def names(outcome):
    return [e["event"] for e in outcome.trace]


def asking(state, *replies):
    """A scripted model that searches once on its first call, then gives the next reply."""
    answers = iter(replies)
    search_tool, _ = make_tools(state, mock_search)
    first = []

    def ask(text):
        if not first:
            first.append(True)
            search_tool("chest", ["dumbbells"])
        return next(answers)

    return ask


def test_a_plan_that_passes_leaves_every_step_in_order():
    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    outcome = handle_request(state.user_message, asking(state, GOOD_PLAN), state)
    assert outcome.kind == "plan" and outcome.retry_fired is False
    assert names(outcome) == [
        "request", "trigger", "model_call", "tool_call", "tool_result", "model_reply", "assumed", "checks", "outcome",
    ]
    by_name = {e["event"]: e for e in outcome.trace}
    assert by_name["request"]["minutes_requested"] == 3
    assert by_name["trigger"]["fired"] is False
    assert by_name["model_call"]["prompt"] == state.user_message and by_name["model_call"]["attempt"] == 0
    assert by_name["model_reply"]["kind"] == "plan"
    assert by_name["assumed"] == {**by_name["assumed"], "model_wrote_marker": False, "code_changed_line_1": False}
    assert by_name["checks"]["passed"] is True and all(by_name["checks"]["results"].values())
    assert by_name["outcome"]["kind"] == "plan" and by_name["outcome"]["retry_fired"] is False


def test_a_retry_shows_the_failed_check_then_the_second_attempt():
    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    outcome = handle_request(state.user_message, asking(state, "not a plan at all", GOOD_PLAN), state)
    assert outcome.kind == "plan" and outcome.retry_fired is True
    checks = [e for e in outcome.trace if e["event"] == "checks"]
    assert [c["attempt"] for c in checks] == [0, 1] and [c["passed"] for c in checks] == [False, True]
    assert checks[0]["results"]["format"] is False and checks[0]["results"]["time"] is None  # stopped at format
    regenerate, = [e for e in outcome.trace if e["event"] == "regenerate"]
    assert regenerate["attempt"] == 1 and regenerate["failures"] == checks[0]["failures"]
    calls = [e for e in outcome.trace if e["event"] == "model_call"]
    assert [c["attempt"] for c in calls] == [0, 1] and "failed these checks" in calls[1]["prompt"]


def test_two_failures_end_in_a_visible_error_with_both_attempts_on_record():
    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    outcome = handle_request(state.user_message, asking(state, "no plan", "still no plan"), state)
    assert outcome.kind == "error" and outcome.text == ERROR_MESSAGE and outcome.retry_fired is True
    assert names(outcome).count("checks") == 2 and names(outcome).count("regenerate") == 1
    last = outcome.trace[-1]
    assert last["event"] == "outcome" and last["kind"] == "error" and last["failures"]


def test_a_code_trigger_ends_the_request_before_any_model_call():
    state = RequestState("My knee hurts.")
    outcome = handle_request(state.user_message, lambda text: GOOD_PLAN, state)
    assert names(outcome) == ["request", "trigger", "outcome"]
    assert outcome.trace[1]["fired"] is True and outcome.trace[1]["word"]
    assert outcome.retry_fired is False


def test_a_direct_path_reply_records_that_the_checks_were_skipped():
    state = RequestState("Legs please.")
    outcome = handle_request(state.user_message, lambda text: "How many minutes do you have?", state)
    checks, = [e for e in outcome.trace if e["event"] == "checks"]
    assert checks["skipped"] is True and checks["reason"] == "direct path: question"


def test_a_spent_budget_is_on_record():
    state = RequestState("I have 20 minutes.")
    state.budget_exceeded = True
    outcome = handle_request(state.user_message, lambda text: GOOD_PLAN, state)
    assert outcome.kind == "error" and outcome.text == BUDGET_MESSAGE
    assert "budget_exceeded" in names(outcome)


def test_the_trace_shows_when_code_wrote_the_assumed_marker():
    state = RequestState("I have 3 minutes.  Chest.")  # the user named no equipment
    outcome = handle_request(state.user_message, asking(state, GOOD_PLAN), state)
    assumed, = [e for e in outcome.trace if e["event"] == "assumed"]
    assert assumed["model_wrote_marker"] is False and assumed["code_changed_line_1"] is True


def test_check_results_name_each_check():
    assert check_results([]) == {name: True for name in CHECK_NAMES}
    mixed = check_results(["level: 'Pull-ups' is a version of pull-ups, which is too advanced for a beginner"])
    assert mixed["level"] is False and mixed["name"] is True and mixed["time"] is True
    early = check_results(["format: the plan has no exercise lines"])
    assert early["format"] is False and all(early[n] is None for n in CHECK_NAMES if n != "format")


def test_each_turn_of_a_conversation_has_its_own_trace():
    class Scripted:
        def __init__(self, replies):
            self.replies = list(replies)

        def __call__(self, text):
            return self.replies.pop(0)

    agent = Scripted(["Is it sore or sharp?", HANDOFF_SENTENCE])
    turns = ["My lower back feels a little off.  Legs please.", "It feels sharp when I bend.  Legs please."]
    first, second = run_conversation(turns, agent_factory=lambda state, search_fn: agent)
    assert first.trace[0]["event"] == "request" and first.trace[0]["message"] == turns[0]
    assert second.trace[0]["event"] == "request" and second.trace[0]["message"] == turns[1]
    assert sum(e["event"] == "model_call" for e in second.trace) == 1  # not carried over from turn one


def test_trace_fields_are_what_a_run_row_saves_and_are_plain_json():
    from homeset.trace import trace_fields

    state = RequestState("I have 3 minutes and dumbbells.  Chest.")
    outcome = handle_request(state.user_message, asking(state, "no plan", GOOD_PLAN), state)
    fields = trace_fields(outcome)
    assert fields["retry_fired"] is True and fields["trace"] == outcome.trace
    assert json.loads(json.dumps(fields)) == fields  # survives the run file round trip
