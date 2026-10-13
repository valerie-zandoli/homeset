import pytest

from homeset.labels import (
    ALIASES,
    BODYWEIGHT_ID,
    EQUIPMENT_LABELS,
    FOCUS_LABELS,
    UnknownLabel,
    equipment_ids,
    focus_filters,
    normalize_equipment,
    normalize_focus,
)


def test_legs_and_core_match_the_agreed_mapping():
    assert focus_filters("legs").muscle_ids == (10, 11, 8, 7, 15)  # Soleus (15) included with calves
    assert focus_filters("core").muscle_ids == (6, 14)
    assert focus_filters("calves").muscle_ids == (7, 15)


def test_no_label_costs_more_than_five_searches():
    assert all(len(f.muscle_ids) <= 5 for f in FOCUS_LABELS.values())


def test_cardio_uses_the_category_not_a_muscle():
    cardio = focus_filters("cardio")
    assert cardio.muscle_ids == () and cardio.category_ids == (15,)


def test_aliases_point_at_real_labels():
    for alias, label in ALIASES.items():
        assert label in FOCUS_LABELS or label in EQUIPMENT_LABELS, alias


def test_aliases_and_case_and_spacing_are_normalized():
    assert normalize_focus("  Lower   Body ") == "legs"
    assert normalize_equipment("Yoga mat") == "mat"
    assert normalize_equipment("weights") == "dumbbells"


def test_unknown_label_raises():
    with pytest.raises(UnknownLabel):
        normalize_focus("wrists")
    with pytest.raises(UnknownLabel):
        normalize_equipment("treadmill")


def test_bodyweight_is_always_added_and_ids_are_sorted():
    assert equipment_ids(["mat", "dumbbells"]) == (3, 4, BODYWEIGHT_ID)
    assert equipment_ids([]) == (BODYWEIGHT_ID,)


def test_household_items_count_as_bodyweight():
    assert equipment_ids(["household items"]) == (BODYWEIGHT_ID,)
