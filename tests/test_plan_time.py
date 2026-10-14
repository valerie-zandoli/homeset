import pytest

from homeset.plan_time import calculate_plan_time, within_band


def ex(sets, reps, rest):
    return {"sets": sets, "reps": reps, "rest_seconds": rest}


def test_one_exercise():
    # 3 sets x 10 reps x 3 s = 90 s of work, plus 3 x 30 s rest = 90 s  ->  180 s = 3.0 min
    assert calculate_plan_time([ex(3, 10, 30)]) == 3.0


def test_transitions_are_added_between_exercises_only():
    one = calculate_plan_time([ex(1, 10, 0)])  # 30 s = 0.5 min
    two = calculate_plan_time([ex(1, 10, 0), ex(1, 10, 0)])  # 30 + 30 + 30 s transition = 1.5 min
    assert (one, two) == (0.5, 1.5)


def test_rounds_to_one_decimal():
    assert calculate_plan_time([ex(1, 10, 5)]) == 0.6  # 35 s = 0.583 min


def test_bad_input_raises_value_error():
    with pytest.raises(ValueError):
        calculate_plan_time([])
    with pytest.raises(ValueError):
        calculate_plan_time([{"sets": 3, "reps": 10}])
    with pytest.raises(ValueError):
        calculate_plan_time([ex(-1, 10, 30)])


def test_band_is_five_minutes_inclusive():
    assert within_band(25, 20) and within_band(15, 20)
    assert not within_band(25.1, 20)


def test_the_prompt_aims_inside_the_pass_band():
    from homeset.plan_time import AIM_MINUTES, BAND_MINUTES
    from homeset.prompt import SYSTEM_PROMPT

    assert AIM_MINUTES < BAND_MINUTES
    assert f"within {AIM_MINUTES} minutes of the requested time" in SYSTEM_PROMPT
    assert "__AIM_MINUTES__" not in SYSTEM_PROMPT
