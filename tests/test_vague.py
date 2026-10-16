"""The code-fired clarifying question for vague symptom wording (homeset/triggers.py:find_vague).

No model, no network.  The case files are the single source of truth for the inputs:  the
ten new vague inputs and three controls (evals/cases/vague_symptoms.json, written before the
code), the five earlier ambiguous inputs, and every earlier input that expects a plan.
"""

import json
from pathlib import Path

import pytest

from homeset.agent import run_conversation
from homeset.checks import HANDOFF_SENTENCE
from homeset.harness import RequestState, handle_request
from homeset.messages import VAGUE_QUESTION
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


# --- the harness path:  code asks the question, the model is never called ---------------------


class ScriptedAgent:
    """Returns the next scripted reply and remembers every message it was sent."""

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.seen = []

    def __call__(self, text):
        self.seen.append(text)
        return self.replies.pop(0)


def factory_for(agent):
    return lambda state, search_fn: agent


@pytest.mark.parametrize("case", VAGUE, ids=[c["id"] for c in VAGUE])
def test_the_harness_asks_the_fixed_question_without_calling_the_model(case):
    agent = ScriptedAgent([case["scripted_reply"]])  # a plan, so a model call would be a visible failure
    outcome = handle_request(case["input"], agent, RequestState(case["input"]))
    assert outcome.kind == "question"
    assert outcome.text == VAGUE_QUESTION
    assert agent.seen == []  # the model was not called
    assert outcome.reason  # the phrase that fired, for the run log
    vague_events = [e for e in outcome.trace if e["event"] == "vague"]
    assert vague_events and vague_events[0]["fired"] is True


def test_a_clear_trigger_in_the_same_message_wins():
    agent = ScriptedAgent()
    outcome = handle_request(
        "My knee feels off and it hurts when I squat.", agent, RequestState("My knee feels off and it hurts when I squat.")
    )
    assert outcome.kind == "handoff" and outcome.text == HANDOFF_SENTENCE and outcome.reason == "hurts"
    assert agent.seen == []


def test_the_answer_turn_reaches_the_model_with_the_earlier_request():
    agent = ScriptedAgent(["How many minutes do you have?"])
    turns = ["My knee feels off.  20 minutes, mat, legs.", "It is just tired."]
    outcomes = run_conversation(turns, agent_factory=factory_for(agent))
    assert outcomes[0].kind == "question" and outcomes[0].text == VAGUE_QUESTION
    assert outcomes[1].kind == "question"  # the scripted model reply
    assert len(agent.seen) == 1  # only the answer turn called the model
    assert "Earlier request: My knee feels off.  20 minutes, mat, legs." in agent.seen[0]
    assert "The user answered: It is just tired." in agent.seen[0]
    assert "step 1" in agent.seen[0]


def test_the_earlier_request_is_passed_once_only():
    agent = ScriptedAgent(["How many minutes do you have?", "How many minutes do you have?"])
    turns = ["My knee feels off.  20 minutes, mat, legs.", "It is just tired.", "Swap the first exercise."]
    run_conversation(turns, agent_factory=factory_for(agent))
    assert "Earlier request" in agent.seen[0]
    assert agent.seen[1] == "Swap the first exercise."


def test_an_answer_that_says_it_hurts_is_handed_off_by_code():
    agent = ScriptedAgent()
    turns = ["My knee feels off.  20 minutes, mat, legs.", "It hurts when I squat."]
    outcomes = run_conversation(turns, agent_factory=factory_for(agent))
    assert [o.kind for o in outcomes] == ["question", "handoff"]
    assert outcomes[1].text == HANDOFF_SENTENCE
    assert agent.seen == []


def test_a_second_vague_message_after_the_question_is_handed_off():
    agent = ScriptedAgent()
    turns = ["My knee feels off.  20 minutes, mat, legs.", "It still feels off and I cannot tell."]
    outcomes = run_conversation(turns, agent_factory=factory_for(agent))
    assert [o.kind for o in outcomes] == ["question", "handoff"]
    assert outcomes[1].reason.startswith("vague again")
    assert agent.seen == []
