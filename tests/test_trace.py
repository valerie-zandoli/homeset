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
