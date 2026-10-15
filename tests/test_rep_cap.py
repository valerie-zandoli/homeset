"""The kettlebell rep cap (homeset/rep_cap.py).  No model, no network.

Yadan set the cap at 8 reps per set on 2026-10-15 (Slack); it matches the beginner
tie-breaker "a first-time exerciser can do 8 clean reps unassisted" (PRD 3d, rule C).
"""

import json
from pathlib import Path

import pytest

from homeset.labels import EQUIPMENT_LABELS
from homeset.rep_cap import KETTLEBELL_ID, KETTLEBELL_MAX_REPS, is_kettlebell_move, over_rep_cap

NAMES = json.loads((Path(__file__).parent / "fixtures" / "wger_english_names.json").read_text())["names"]


def test_the_cap_is_eight_and_the_id_matches_the_label_table():
    assert KETTLEBELL_MAX_REPS == 8
    assert KETTLEBELL_ID == EQUIPMENT_LABELS["kettlebell"]


@pytest.mark.parametrize(
    "name, ids, expected",
    [
        ("Kettlebell Swing", [], True),  # named
        ("Turkish Get-Up with Kettle Bell", [], True),  # "kettle bell" written as two words
        ("Goblet Squat", [10], True),  # tagged, not named
        ("Goblet Squat", [3], False),  # tagged dumbbell
        ("Dumbbell Goblet Squat", [], False),
        ("Push-Up", [7], False),
        ("Bird Dog", [], False),
    ],
)
def test_what_counts_as_a_kettlebell_move(name, ids, expected):
    assert is_kettlebell_move(name, ids) is expected


@pytest.mark.parametrize(
    "reps, expected",
    [(5, False), (8, False), (9, True), (10, True), (15, True)],
)
def test_the_cap_is_per_set_and_eight_passes(reps, expected):
    assert over_rep_cap("Kettlebell Swing", reps, [10]) is expected


def test_other_equipment_is_not_capped():
    assert over_rep_cap("Dumbbell Goblet Squat", 12, [3]) is False
    assert over_rep_cap("Push-Up", 20, [7]) is False


def test_real_names_that_this_would_cap(capsys):
    """Lists every one of the real English names the cap applies to, so a reader can judge it."""
    capped = sorted(n for n in NAMES if is_kettlebell_move(n))
    with capsys.disabled():
        print(f"\nkettlebell names in the {len(NAMES)} real English names: {len(capped)}")
        for n in capped:
            print("  ", n)
    assert capped, "the fixture should hold at least one kettlebell name"
    assert all("kettle" in n.lower() for n in capped)


# --- the cap inside the output checks, the retry, and the prompt (no model) ---

from homeset.checks import SAFETY_LINE, check_plan  # noqa: E402
from homeset.harness import RequestState, handle_request  # noqa: E402
from homeset.prompt import SYSTEM_PROMPT  # noqa: E402

KNOWN = {"Kettlebell Swing": [10], "Dumbbell Goblet Squat": [3]}


def kettlebell_plan(reps, name="Kettlebell Swing", gear="kettlebell"):
    # 3 sets x reps x 3 s + 3 x 30 s, then the 30 s transition (plan_time), kept simple by asking for 3 min
    return "\n".join(
        [
            "HomeSet plan: 3 min, kettlebell, full body",
            f"1. {name} ({gear}): 3 sets x {reps} reps, rest 30 s",
            "Total time: 3.0 min (calculated)",
            SAFETY_LINE,
        ]
    )


def reps_failures(text):
    return [f for f in check_plan(text, KNOWN, {10, 7}, requested_minutes=3) if f.startswith("reps:")]


def test_eight_reps_on_a_kettlebell_move_passes_and_nine_fails():
    assert reps_failures(kettlebell_plan(8)) == []
    failures = reps_failures(kettlebell_plan(9))
    assert len(failures) == 1 and "capped at 8 reps per set" in failures[0]


def test_a_dumbbell_move_is_not_capped():
    text = "\n".join(
        [
            "HomeSet plan: 3 min, dumbbells, legs",
            "1. Dumbbell Goblet Squat (dumbbell): 3 sets x 12 reps, rest 30 s",
            "Total time: 3.0 min (calculated)",
            SAFETY_LINE,
        ]
    )
    assert [f for f in check_plan(text, KNOWN, {3, 7}, requested_minutes=3) if f.startswith("reps:")] == []


def test_an_over_cap_plan_is_regenerated_once_and_then_passes():
    state = RequestState("I have 3 minutes and a kettlebell.  Full body.")
    state.known_exercises = dict(KNOWN)
    state.owned_equipment_ids = {10, 7}
    state.requested_minutes = 3
    answers = iter([kettlebell_plan(12), kettlebell_plan(8)])
    prompts = []

    def ask(text):
        prompts.append(text)
        return next(answers)

    outcome = handle_request(state.user_message, ask, state)
    assert len(prompts) == 2 and "capped at 8 reps per set" in prompts[1]
    assert outcome.kind == "plan" and outcome.failures == []


def test_a_plan_that_stays_over_cap_never_reaches_the_user():
    state = RequestState("I have 3 minutes and a kettlebell.  Full body.")
    state.known_exercises = dict(KNOWN)
    state.owned_equipment_ids = {10, 7}
    state.requested_minutes = 3
    outcome = handle_request(state.user_message, lambda text: kettlebell_plan(12), state)
    assert outcome.kind == "error"
    assert "Kettlebell Swing" not in outcome.text


def test_the_prompt_states_the_cap_from_the_module():
    assert "use no more than 8 reps per set" in SYSTEM_PROMPT
    assert "__KETTLEBELL_MAX_REPS__" not in SYSTEM_PROMPT
