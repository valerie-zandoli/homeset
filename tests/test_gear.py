"""The name-based gear check (homeset/gear.py).  No model, no network.

Cases come from the 2026-10-14 grading of request set A:  wger tagged "Biceps with TRX" as
bodyweight, "Medicine ball twist" as a Swiss ball, and "Fly With Dumbbells, Decline Bench"
as a plain bench, so the equipment check passed plans that needed other gear.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))  # reuse the raw-exercise helpers from test_wger

from homeset import wger  # noqa: E402
from homeset.gear import UNAVAILABLE_GEAR_ID, gear_ids_from_name  # noqa: E402
from test_wger import Resp, no_sleep, raw  # noqa: E402


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Biceps with TRX", {UNAVAILABLE_GEAR_ID}),
        ("Medicine ball twist", {UNAVAILABLE_GEAR_ID}),
        ("Fly With Dumbbells, Decline Bench", {UNAVAILABLE_GEAR_ID, 3, 8}),
        ("Double Kettlebell Front Squat", {UNAVAILABLE_GEAR_ID, 10}),
        ("Calf press using leg press machine", {UNAVAILABLE_GEAR_ID}),
        ("Jump rope: basic jumps", {UNAVAILABLE_GEAR_ID}),
        ("Front raises with plates", {UNAVAILABLE_GEAR_ID}),
        ("Dumbbell or Machine Calf Raise", {3}),  # the machine is an alternative
        ("Benchpress Dumbbells", {3, 8}),
        ("Incline bench press - dumbbell", {3, 8, 9}),
        ("Banded Clamshell", {11}),
        ("rubber band glute kickback", {11}),
        ("Pull-ups", {6}),
        ("Australian pull-ups", {6}),
        ("Cable Front Raise with a small bar", {12}),
        ("Biceps Curls With SZ-bar", {2}),
        ("Swiss ball crunch", {5}),
    ],
)
def test_the_name_implies_the_gear(name, expected):
    assert gear_ids_from_name(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "Push-Up",
        "Wide Push-Up",
        "Decline Push-Up",
        "Incline Push-Up",
        "Bodyweight Squat HD",
        "Pike Hold (Floor)",
        "Squat -> Stand Coordination",
        "Standing IT band stretch",
        "Single Leg Glute Bridge",
        "Hip Raise, Lying",
        "Bird Dog",
        "Kneeling kickbacks",
    ],
)
def test_names_without_gear_imply_none(name):
    assert gear_ids_from_name(name) == set()


def test_the_client_adds_the_name_gear_to_the_exercise_ids():
    record = wger.clean_exercise(raw(1, "Biceps with TRX", [7]))
    assert UNAVAILABLE_GEAR_ID in record["equipment_ids"] and 7 in record["equipment_ids"]


def search_with(rows, equipment):
    page = {"count": len(rows), "next": None, "results": rows}

    def get(url, params, timeout):
        return Resp(200, page)

    result = wger.search_exercises("chest", equipment, get=get, sleep=no_sleep)
    return [e["name"] for g in result["groups"] for e in g["exercises"]]


def test_a_user_with_no_equipment_is_never_offered_a_trx_or_machine_move():
    rows = [raw(1, "Biceps with TRX", [7]), raw(2, "Leverage machine chest press", [7]), raw(3, "Push-Up", [7])]
    assert sorted(set(search_with(rows, ["nothing"]))) == ["Push-Up"]


def test_a_gear_move_stays_when_the_user_owns_that_gear():
    rows = [raw(1, "Banded Clamshell", [11]), raw(2, "Push-Up", [7]), raw(3, "Dumbbell Floor Press", [3])]
    assert sorted(set(search_with(rows, ["band"]))) == ["Banded Clamshell", "Push-Up"]


def test_a_name_that_needs_a_second_kind_of_gear_is_dropped_without_it():
    rows = [raw(1, "Benchpress Dumbbells", [3]), raw(2, "Dumbbell Floor Press", [3])]
    assert sorted(set(search_with(rows, ["dumbbells"]))) == ["Dumbbell Floor Press"]  # the tag lacks the bench
    assert sorted(set(search_with(rows, ["dumbbells", "bench"]))) == ["Benchpress Dumbbells", "Dumbbell Floor Press"]


def test_the_graded_set_a_plans_that_needed_other_gear_are_now_dropped():
    # a04, a05, a11, a15 from the 2026-10-14 grading, with the equipment ids wger tagged.
    cases = {
        "a04": ({10, 7}, "Double Kettlebell Front Squat", [10]),
        "a05": ({3, 8, 7}, "Fly With Dumbbells, Decline Bench", [3, 8]),
        "a11": ({5, 7}, "Medicine ball twist", [5]),
        "a15": ({7}, "Biceps with TRX", [7]),
    }
    for case, (owned, name, tags) in cases.items():
        record = wger.clean_exercise(raw(1, name, tags))
        assert not set(record["equipment_ids"]) <= owned, case


def test_graded_exercises_that_were_fine_are_not_newly_dropped():
    fine = {
        "Dumbbell Floor Press": [3], "One-Arm Dumbbell Row": [3], "Shoulder Press, Dumbbells": [3],
        "Biceps Curls With Dumbbell": [3], "Hammer Curls": [3], "Kettlebell deadlifts": [10],
        "Seated Band Row": [11], "Squats": [1], "Biceps Curls With SZ-bar": [2], "Push-Up": [7],
        "Banded Front Raise": [11], "Dumbbell or Machine Calf Raise": [3], "Dumbbell Calf Raise": [3],
    }
    for name, tags in fine.items():
        record = wger.clean_exercise(raw(1, name, tags))
        assert set(record["equipment_ids"]) <= set(tags) | {7}, (name, record["equipment_ids"])


def test_gear_words_appear_in_a_minority_of_real_names():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "wger_english_names.json").read_text())
    with_gear = [n for n in fixture["names"] if gear_ids_from_name(n)]
    assert 0 < len(with_gear) < len(fixture["names"]) * 0.4  # a guard against a runaway pattern
