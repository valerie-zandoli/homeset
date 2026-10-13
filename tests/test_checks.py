from homeset.checks import HANDOFF_SENTENCE, SAFETY_LINE, check_plan, classify, parse_plan

KNOWN = {"Push-ups": [7], "Fly With Dumbbells": [3], "Decline Bench Press Dumbbell": [8, 3]}
OWNED = {3, 4, 7}  # mat, dumbbells, bodyweight


def plan(lines=None, total="3.0", first="HomeSet plan: 20 min, mat and dumbbells, chest", safety=SAFETY_LINE):
    body = lines or ["1. Push-ups (none (bodyweight exercise)): 3 sets x 10 reps, rest 30 s"]
    return "\n".join([first, *body, f"Total time: {total} min (calculated)", safety])


def test_classify_handoff_error_question_plan():
    assert classify(HANDOFF_SENTENCE) == "handoff"
    assert classify("I could not reach the exercise database.  Try again?") == "error"
    assert classify("How many minutes do you have?") == "question"
    assert classify(plan()) == "plan"


def test_a_good_plan_passes():
    # 3 sets x 10 reps x 3 s + 3 x 30 s = 3.0 min; the request was 3 minutes
    assert check_plan(plan(), KNOWN, OWNED, requested_minutes=3) == []


def test_invented_exercise_fails_the_name_check():
    text = plan(["1. Burpee Pushups (none (bodyweight exercise)): 3 sets x 10 reps, rest 30 s"])
    failures = check_plan(text, KNOWN, OWNED, requested_minutes=3)
    assert any(f.startswith("name:") for f in failures)


def test_exercise_that_needs_a_bench_fails_the_equipment_check():
    text = plan(["1. Decline Bench Press Dumbbell (bench): 3 sets x 10 reps, rest 30 s"])
    failures = check_plan(text, KNOWN, OWNED, requested_minutes=3)
    assert any(f.startswith("equipment:") for f in failures)


def test_total_outside_the_band_fails():
    failures = check_plan(plan(), KNOWN, OWNED, requested_minutes=20)
    assert any(f.startswith("time:") for f in failures)


def test_stated_total_must_match_the_codes_sum():
    failures = check_plan(plan(total="9.0"), KNOWN, OWNED, requested_minutes=3)
    assert any(f.startswith("total:") for f in failures)


def test_missing_safety_line_fails():
    failures = check_plan(plan(safety="Have fun!"), KNOWN, OWNED, requested_minutes=3)
    assert any(f.startswith("safety line:") for f in failures)


def test_bad_format_fails_with_a_format_message():
    failures = check_plan("Here is your plan: do some push-ups.", KNOWN, OWNED, requested_minutes=3)
    assert failures and failures[0].startswith("format:")


def test_names_match_without_regard_to_case():
    text = plan(["1. PUSH-UPS (none (bodyweight exercise)): 3 sets x 10 reps, rest 30 s"])
    assert check_plan(text, KNOWN, OWNED, requested_minutes=3) == []


def test_parse_plan_reads_each_exercise_line():
    parsed = parse_plan(plan())
    assert parsed.exercises[0]["name"] == "Push-ups"
    assert (parsed.exercises[0]["sets"], parsed.exercises[0]["reps"], parsed.exercises[0]["rest_seconds"]) == (3, 10, 30)


def test_names_with_parentheses_are_read_from_the_known_names():
    # Found by the first live Eval Card run:  "Pike Hold (Floor)" was split at its own parenthesis.
    known = {"Pike Hold (Floor)": [7], "Arm Raises (T/Y/I)": [7]}
    text = plan([
        "1. Pike Hold (Floor) (none (bodyweight exercise)): 3 sets x 10 reps, rest 30 s",
        "2. Arm Raises (T/Y/I) (bodyweight): 3 sets x 10 reps, rest 30 s",
    ], total="6.5")
    assert check_plan(text, known, OWNED, requested_minutes=6.5) == []


def test_an_unknown_name_with_parentheses_is_reported_by_name():
    text = plan(["1. Burpee (Floor) (bodyweight): 3 sets x 10 reps, rest 30 s"])
    failures = check_plan(text, KNOWN, OWNED, requested_minutes=3)
    assert any(f.startswith("name:") and "Burpee" in f for f in failures)


def test_every_fixed_message_is_recognized_without_the_plan_checks():
    from homeset import messages as m

    assert classify(m.UNREACHABLE) == "error"
    for text in (
        m.NO_MATCH.replace("<focus>", "calves").replace("<equipment>", "a pull-up bar"),
        m.TOO_FEW.replace("<n>", "2").replace("<focus>", "legs").replace("<equipment>", "a mat")
        .replace("<minutes>", "30").replace("<shorter>", "10"),
        m.OUT_OF_RANGE.replace("<n>", "2"),
        m.MISSING_MINUTES,
        m.UNKNOWN_LABEL.replace("<focus or equipment>", "equipment").replace("<the closest labels>", "mat or band"),
    ):
        assert classify(text) == "question", text


def test_a_plan_is_never_mistaken_for_a_message():
    assert classify(plan()) == "plan"
