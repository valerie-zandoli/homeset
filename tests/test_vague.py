"""The code-fired clarifying question for vague symptom wording (homeset/triggers.py:find_vague).

No model, no network.  The case files are the single source of truth for the inputs:  the
ten new vague inputs and three controls (evals/cases/vague_symptoms.json, written before the
code), the five earlier ambiguous inputs, and every earlier input that expects a plan.
"""

import json
from pathlib import Path

import pytest

from homeset.triggers import find_trigger, find_vague

CASES_DIR = Path(__file__).resolve().parents[1] / "evals" / "cases"


def load(name):
    return json.loads((CASES_DIR / name).read_text())["cases"]


def inputs_of(case):
    return [t["input"] for t in case["turns"]] if "turns" in case else [case["input"]]


VAGUE = [c for c in load("vague_symptoms.json") if c["expect"]["kind"] == "question"]
CONTROLS = [c for c in load("vague_symptoms.json") if c["expect"]["kind"] == "plan"]


@pytest.mark.parametrize("case", VAGUE, ids=[c["id"] for c in VAGUE])
def test_each_vague_input_fires_and_is_not_a_clear_trigger(case):
    assert find_vague(case["input"]), case["input"]
    assert find_trigger(case["input"]) is None  # the question path, not the hand-off path


@pytest.mark.parametrize("case", CONTROLS, ids=[c["id"] for c in CONTROLS])
def test_each_control_stays_quiet(case):
    assert find_vague(case["input"]) is None


def test_the_five_earlier_ambiguous_inputs_now_fire():
    earlier = [load("refusals_5.json")[3]] + [
        c for c in load("refusals_variants.json") if c["group"] == "ambiguous"
    ]
    assert len(earlier) == 5
    for case in earlier:
        assert find_vague(case["input"]), case["id"]


def test_no_earlier_input_that_expects_a_plan_fires():
    # A false question costs the user a message, so every ordinary request must stay quiet.
    checked = 0
    for name in (
        "controls.json", "requests_20.json", "edge_cases.json", "injection.json", "eval_card.json",
        "multi_turn.json", "regressions.json", "refusals_variants.json",
    ):
        for case in load(name):
            turns = case["turns"] if "turns" in case else [case]
            for turn in turns:
                if "input" in turn and turn.get("expect", {}).get("kind") == "plan":
                    checked += 1
                    assert find_vague(turn["input"]) is None, (name, case["id"], turn["input"])
    assert checked >= 35  # the walk really found the plan-expecting inputs (38 on 2026-10-16)


@pytest.mark.parametrize(
    "text",
    [
        "I am sore from yesterday's leg day.  20 minutes, no equipment, upper body.",  # soreness is not vague
        "My legs are tired.  15 minutes, mat, legs.",
        "I feel strong today.  20 minutes, dumbbells, arms.",
        "Please tweak the plan.  20 minutes, mat, legs.",
        "Do not bother with a warm up.  15 minutes, mat, core.",
        "There is no discomfort and no ache.  20 minutes, mat, legs.",
        "My knee does not feel off at all.  20 minutes, mat, legs.",
    ],
)
def test_ordinary_wording_stays_quiet(text):
    assert find_vague(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "my knee feels off",
        "My knee FEELS OFF.",
        "It has been feeling a little bit weird.",
        "I felt kind of odd after the last set.",
        "It doesn't feel right.",
        "It does not feel quite right.",
        "Something is off with my shoulder.",
        "That has been bothering me.",
        "A twinge in my hip.",
        "It is aching.",
    ],
)
def test_vague_wording_fires(text):
    assert find_vague(text)


def test_a_message_with_both_goes_to_the_hand_off_because_the_trigger_is_checked_first():
    # The harness checks find_trigger first, so a message with both goes to the hand-off.
    text = "My knee feels off and it hurts when I squat."
    assert find_trigger(text) == "hurts"
    assert find_vague(text)  # both fire; the order in the harness decides, and the trigger wins
