"""The "(assumed)" marker is written by code (README open item 8).  No model, no network.

The set A test reads the approved case file, so the 20 requests and their "assumed"
expectations are the single source of truth.
"""

import json
from pathlib import Path

import pytest

from homeset.assumed import equipment_stated, focus_stated, mark_assumed
from homeset.harness import RequestState, handle_request

CASES = json.loads((Path(__file__).resolve().parents[1] / "evals" / "cases" / "requests_20.json").read_text())["cases"]
SAFETY = "Stop if anything hurts.  For pain or injury, see a doctor or physical therapist."


def plan(line1: str) -> str:
    return f"{line1}\n1. Push-up (nothing): 3 sets x 10 reps, rest 30 s\nTotal time: 3.0 min (calculated)\n{SAFETY}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_every_set_a_request_gets_the_marker_exactly_where_expected(case):
    assumed = case["expect"]["assumed"]
    assert equipment_stated(case["input"]) == ("equipment" not in assumed)
    assert focus_stated(case["input"]) == ("focus" not in assumed)


def test_a15_gets_the_equipment_marker_even_when_the_model_forgets_it():
    text = mark_assumed(plan("HomeSet plan: 20 min, nothing, arms"), "I have 20 minutes.  Arms.")
    assert text.splitlines()[0] == "HomeSet plan: 20 min, nothing (assumed), arms"


def test_both_missing_marks_both():
    text = mark_assumed(plan("HomeSet plan: 20 min, nothing, full body"), "I have 20 minutes.")
    assert text.splitlines()[0] == "HomeSet plan: 20 min, nothing (assumed), full body (assumed)"


def test_stated_equipment_loses_a_marker_the_model_added():
    for user in ("I have 20 minutes and no equipment.  Arms.", "I have 30 minutes and nothing but my body.  Core."):
        text = mark_assumed(plan("HomeSet plan: 20 min, nothing (assumed), arms"), user)
        assert "(assumed)" not in text.splitlines()[0]


def test_the_marker_follows_a_parenthetical_and_a_comma_inside_it():
    line1 = "HomeSet plan: 25 min, household items (chair, towel), thighs"
    text = mark_assumed(plan(line1), "I have 25 minutes.  Thighs.")
    assert text.splitlines()[0] == "HomeSet plan: 25 min, household items (chair, towel) (assumed), thighs"


@pytest.mark.parametrize(
    "message, equipment, focus",
    [
        ("Give me a 15-minute leg workout.", False, True),  # singular "leg"
        ("I have 20 minutes and a band.  I am back from a break and feel weak.", True, False),  # "back" the adverb
        ("I have 20 minutes and two dumbell, focus on thighs and butt.", True, True),  # misspelling
        ("I have 20 minutes and a chair.  Biceps.", True, True),  # household word, muscle word
        ("I am sore from yesterday's workout.  I have 20 minutes and no equipment.", True, False),
        ("I want a 2-minute full-body workout.", False, True),  # hyphenated focus
        ("Work on my back with a pull-up bar.", True, True),  # "back" the body part
        ("I have 20 minutes.", False, False),
        ("I am a coach and I have my own back garden.  20 minutes.", False, True),  # known limit: "back" noun
    ],
)
def test_stated_detection_on_tricky_wording(message, equipment, focus):
    assert equipment_stated(message) is equipment
    assert focus_stated(message) is focus


def test_text_that_is_not_a_plan_is_left_alone():
    for text in ("How many minutes do you have?", "I cannot plan workouts around pain.", ""):
        assert mark_assumed(text, "I have 20 minutes.") == text


def test_the_harness_returns_the_marked_plan_and_the_checks_still_pass():
    state = RequestState("I have 3 minutes and dumbbells.")  # focus not named
    state.known_exercises = {"Push-up": [7]}
    state.owned_equipment_ids = {7}
    text = plan("HomeSet plan: 3 min, dumbbells, chest")
    outcome = handle_request(state.user_message, lambda _t: text, state)
    assert outcome.kind == "plan", outcome.failures
    assert outcome.text.splitlines()[0] == "HomeSet plan: 3 min, dumbbells, chest (assumed)"


def test_equipment_named_in_an_earlier_turn_still_counts_in_a_follow_up():
    state = RequestState("I have 20 minutes, a mat, and dumbbells.  Legs.")
    state.reset_for("Swap the first exercise for something else.")
    text = mark_assumed(plan("HomeSet plan: 20 min, mat and dumbbells, legs"), state.conversation_text)
    assert "(assumed)" not in text.splitlines()[0]
