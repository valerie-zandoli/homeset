"""The trace of a request, tested with no model and no network."""

from homeset.checks import HANDOFF_SENTENCE
from homeset.harness import RequestState, handle_request
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
