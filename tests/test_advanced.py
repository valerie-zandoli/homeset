"""The blocked advanced-move list (homeset/advanced.py).  No model, no network.

Cases come from the 2026-10-14 grading of request set A:  a04 gave a beginner "Single Arm
Plank to Row 3x8" and a06 gave "Pull-ups 3x8" (P3 N), and the 2026-10-15 rulings on the
five P3 rows (a04 and a06 too hard; Hollow Hold and Floor dips fine).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))  # reuse the raw-exercise helpers from test_wger

from homeset import wger  # noqa: E402
from homeset.advanced import blocked_move  # noqa: E402
from homeset.checks import SAFETY_LINE, check_plan  # noqa: E402
from test_wger import Resp, no_sleep, raw  # noqa: E402


@pytest.mark.parametrize(
    "name, move",
    [
        ("Single Arm Plank to Row", "Single Arm Plank to Row"),
        ("single-arm plank-to-row", "Single Arm Plank to Row"),
        ("Pull-ups", "Pull-ups"),
        ("Pull Ups", "Pull-ups"),
        ("pullups", "Pull-ups"),
        ("Pull-Ups (Wide Grip)", "Pull-ups"),
        ("Reverse-grip pull-ups", "Pull-ups"),
        ("Archer Pull Up", "Pull-ups"),
    ],
)
def test_blocked_moves_are_caught_in_any_spelling(name, move):
    assert blocked_move(name) == move


@pytest.mark.parametrize(
    "name",
    [
        "Hollow Hold",  # ruled fine 2026-10-15 (a08)
        "Floor dips",  # ruled fine 2026-10-15 (a15, a19)
        "Assisted Pull-Up",  # an easier version
        "Australian pull-ups",  # an inverted row
        "Pull-up Isometric Hold",  # not ruled on
        "Leg raises pull up bar",  # names the bar, not the move
        "Plank",
        "Bent Over Dumbbell Row",
        "Chin Up",  # on the proposed list, not yet ruled on
        "Push-Up",
    ],
)
def test_allowed_moves_are_not_blocked(name):
    assert blocked_move(name) is None


def test_every_real_name_the_list_blocks():
    # A guard against a runaway pattern:  if wger adds a name, this list shows it for review.
    fixture = json.loads((Path(__file__).parent / "fixtures" / "wger_english_names.json").read_text())
    blocked = sorted(n for n in fixture["names"] if blocked_move(n))
    assert blocked == sorted(
        [
            "Archer Pull Up",
            "Front lever pull-up",
            "L-Sit Pull-ups",
            "Neutral-grip pull-ups or TRX rows",
            "Pull Ups on Machine",
            "Pull-Ups (Neutral Grip)",
            "Pull-Ups (Wide Grip)",
            "Pull-ups",
            "Pullup on fingerboard",
            "Reverse-grip pull-ups",
            "Single Arm Plank to Row",
            "Typewriter Pull-ups",
            "commando pull-ups",
        ]
    )


def search_with(rows, equipment, focus="back"):
    page = {"count": len(rows), "next": None, "results": rows}

    def get(url, params, timeout):
        return Resp(200, page)

    return wger.search_exercises(focus, equipment, get=get, sleep=no_sleep)


def test_the_graded_set_a_moves_never_reach_the_model():
    # a04 (kettlebell) and a06 (pull-up bar), with the equipment ids wger tagged.
    rows = [raw(1, "Single Arm Plank to Row", [10]), raw(2, "Kettlebell Swing", [10])]
    result = search_with(rows, ["kettlebell"], focus="full body")
    names = {e["name"] for g in result["groups"] for e in g["exercises"]}
    assert "Single Arm Plank to Row" not in names and "Kettlebell Swing" in names

    rows = [raw(1, "Pull-ups", [6]), raw(2, "Assisted Pull-Up", [6])]
    result = search_with(rows, ["pull-up bar"])
    names = {e["name"] for g in result["groups"] for e in g["exercises"]}
    assert names == {"Assisted Pull-Up"}
    assert all(g["blocked_advanced"] >= 1 for g in result["groups"])


def test_a_plan_that_still_names_a_blocked_move_fails_the_check():
    known = {"Pull-ups": [6], "Assisted Pull-Up": [6]}
    text = "\n".join(
        [
            "HomeSet plan: 3 min, pull-up bar, back",
            "1. Pull-ups (pull-up bar): 3 sets x 10 reps, rest 30 s",
            "Total time: 3.0 min (calculated)",
            SAFETY_LINE,
        ]
    )
    failures = check_plan(text, known, {6, 7}, requested_minutes=3)
    assert any(f.startswith("level:") for f in failures)

    allowed = text.replace("Pull-ups", "Assisted Pull-Up")
    assert check_plan(allowed, known, {6, 7}, requested_minutes=3) == []
