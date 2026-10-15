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
