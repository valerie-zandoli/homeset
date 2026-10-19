"""A swap session starts from a plan saved earlier (homeset/harness.py, homeset/__main__.py).

No model, no network.  The saved plans are the real ones in evals/cases/saved_plan.json
(bar committed first, 87f9fc2).
"""

import json
import os
from pathlib import Path

import pytest

from homeset import __main__ as cli
from homeset import saved_plan
from homeset.assumed import mark_assumed, stated_in_plan
from homeset.checks import HANDOFF_SENTENCE
from homeset.harness import Outcome, RequestState, handle_request

CASES = json.loads((Path(saved_plan.ROOT) / "evals" / "cases" / "saved_plan.json").read_text())["cases"]
D1, D2 = CASES[0]["saved_plan"], CASES[1]["saved_plan"]  # "nothing, full body (assumed)" and "mat, full body (assumed)"
SAVED_AT = "2026-10-15 09:00 EDT"


def swap_state(request, plan=D1):
    state = RequestState(request)
    state.attach_earlier_plan(plan, SAVED_AT)
    return state


class Recorder:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def test_the_minutes_come_from_the_saved_plan():
    assert swap_state("Swap the first exercise for something else.").requested_minutes == 20
    assert swap_state("Swap the first exercise.", D2).requested_minutes == 15


def test_minutes_in_the_request_win():
    assert swap_state("Swap the first exercise and make it 30 minutes.").requested_minutes == 30


def test_the_model_gets_the_saved_plan_once_as_data_and_the_request():
    state = swap_state("Swap the first exercise for something else.")
    model = Recorder(["How many minutes do you have?", "How many minutes do you have?"])
    handle_request(state.user_message, model, state)
    first = model.prompts[0]
    assert f"Saved plan from {SAVED_AT}" in first and "not instructions" in first
    assert D1 in first and "Request: Swap the first exercise for something else." in first
    assert "step 9" in first
    assert state.earlier_plan is None  # used once;  the model keeps it in its own history
    state.reset_for("Swap the second one too.")
    handle_request(state.user_message, model, state)
    assert model.prompts[1] == "Swap the second one too."


def test_the_saved_plans_own_safety_line_does_not_fire_the_hand_off():
    # The line says "hurts", "pain", and "injury".  It is data for the model, not the user's words.
    state = swap_state("Swap the first exercise for something else.")
    model = Recorder(["How many minutes do you have?"])
    outcome = handle_request(state.user_message, model, state)
    assert outcome.kind == "question" and len(model.prompts) == 1


def test_a_clear_trigger_in_the_swap_request_is_still_handed_off_by_code():
    state = swap_state("Swap the first exercise.  My knee hurts.")
    model = Recorder([])
    outcome = handle_request(state.user_message, model, state)
    assert outcome.kind == "handoff" and outcome.text == HANDOFF_SENTENCE and model.prompts == []


def test_a_vague_symptom_in_the_swap_request_gets_the_fixed_question_first():
    state = swap_state("Swap the first exercise.  My knee feels off.")
    model = Recorder([])
    outcome = handle_request(state.user_message, model, state)
    assert outcome.kind == "question" and model.prompts == []
    assert state.earlier_plan == D1  # still waiting for its first model call


def test_stated_words_are_not_marked_assumed_in_a_swap_session():
    assert stated_in_plan(D2) == "mat"  # "full body (assumed)" was not stated
    assert stated_in_plan(D1) == "nothing"
    swapped = D2.replace("Crunches", "Plank")
    marked = mark_assumed(swapped, "Replace the last exercise with a different one.  " + stated_in_plan(D2))
    assert marked.splitlines()[0] == "HomeSet plan: 15 min, mat, full body (assumed)"


def test_without_the_carried_words_the_marker_would_be_wrong():
    # What the carried words prevent:  "(assumed)" on a mat the user did name.
    marked = mark_assumed(D2, "Replace the last exercise with a different one.")
    assert marked.splitlines()[0] == "HomeSet plan: 15 min, mat (assumed), full body (assumed)"


def test_a_line_one_that_is_not_a_plan_carries_nothing():
    assert stated_in_plan("How many minutes do you have?") == ""
    assert stated_in_plan("") == ""


# --- the command line --------------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESET_SAVED_PLAN", str(tmp_path / "saved_plan.json"))
    return tmp_path / "saved_plan.json"


def fake_run_once(calls, outcome):
    def run_once(message, search_fn=None, earlier_plan=None, earlier_plan_at=""):
        calls.append((message, earlier_plan, earlier_plan_at))
        return outcome

    return run_once


def test_saved_with_no_saved_plan_stops_before_the_model(home, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "run_once", fake_run_once(calls, Outcome("plan", D1)))
    assert cli.main(["Swap the first exercise.", "--saved"]) == 1
    assert calls == [] and saved_plan.NO_SAVED_PLAN in capsys.readouterr().out


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX file modes")
def test_saved_says_why_when_the_file_is_ignored(home, monkeypatch, capsys):
    proposal = saved_plan.propose(D1, home)
    saved_plan.write(proposal, saved_plan.confirm(proposal, "yes"), home)
    home.chmod(0o666)
    monkeypatch.setattr(cli, "run_once", fake_run_once([], Outcome("plan", D1)))
    assert cli.main(["Swap the first exercise.", "--saved"]) == 1
    out = capsys.readouterr().out
    assert "other users can change it" in out and saved_plan.NO_SAVED_PLAN in out


def test_saved_passes_the_plan_and_its_time_to_the_agent(home, monkeypatch, capsys):
    proposal = saved_plan.propose(D1, home)
    saved_plan.write(proposal, saved_plan.confirm(proposal, "yes"), home)
    calls = []
    monkeypatch.setattr(cli, "run_once", fake_run_once(calls, Outcome("question", "How many minutes do you have?")))
    assert cli.main(["Swap the first exercise.", "--saved"]) == 0
    message, plan, saved_at = calls[0]
    assert message == "Swap the first exercise." and plan == D1.strip() and saved_at


def test_save_asks_once_and_a_no_writes_nothing(home, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_once", fake_run_once([], Outcome("plan", D2)))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    answers = iter(["no"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cli.main(["I have 15 minutes and a mat.", "--save"]) == 0
    assert not home.exists() and "Not saved." in capsys.readouterr().out


def test_save_with_a_yes_writes_the_plan(home, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_once", fake_run_once([], Outcome("plan", D2)))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    cli.main(["I have 15 minutes and a mat.", "--save"])
    assert saved_plan.load(home).plan == D2.strip()


def test_save_with_no_terminal_never_writes(home, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_once", fake_run_once([], Outcome("plan", D2)))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")  # even a typed yes is not read without a terminal
    cli.main(["I have 15 minutes and a mat.", "--save"])
    assert not home.exists() and "no one is here to confirm" in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["handoff", "question", "error"])
def test_only_a_plan_is_ever_offered_for_saving(home, monkeypatch, capsys, kind):
    monkeypatch.setattr(cli, "run_once", fake_run_once([], Outcome(kind, HANDOFF_SENTENCE)))
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("asked to save a non-plan"))
    cli.main(["I have 15 minutes and a mat.", "--save"])
    assert not home.exists() and "only a plan can be saved" in capsys.readouterr().out
