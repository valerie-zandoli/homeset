"""Command line:  python -m homeset "I have 20 minutes, a mat, and dumbbells.  Work on legs."

Add --mock to use canned wger data instead of the network (the model call still needs
the API key in .env).  Add --trace to print the step-by-step trace of the request.

Health question (LaNice, 2026-10-19):  before the first plan, code asks about pain, injury, surgery, pregnancy, and medical
conditions.  At a terminal you answer it here;  with no terminal it prints the question and stops.  Add --no-health-issues
to say in the command that you have none (for scripts).  A swap of a saved plan from the last 7 days skips the question.

Save and swap (Build Time, Learn 08):
    python -m homeset "I have 20 minutes and a mat.  Legs." --save
        After a plan, shows it next to the saved plan and asks once;  only the answer "yes" saves.
    python -m homeset "Swap the first exercise for something else." --saved [--save]
        Starts from the saved plan (read-only, automatic);  add --save to offer saving the swap.
"""

from __future__ import annotations

import sys

from . import saved_plan
from .agent import run_once
from .screen import SCREEN_REASON, Screen
from .trace import format_trace


USAGE = 'usage: python -m homeset "your request" [--mock] [--trace] [--save] [--saved] [--no-health-issues]'
FLAGS = {"--mock", "--trace", "--save", "--saved", "--no-health-issues"}


def main(argv: list[str]) -> int:
    unknown = [a for a in argv if a.startswith("--") and a not in FLAGS]
    if unknown:  # a misspelled --save would otherwise run as a normal request with no checkpoint
        print(f"Unknown option: {' '.join(unknown)}")
        print(USAGE)
        return 2
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(USAGE)
        return 2
    search_fn = None
    if "--mock" in argv:
        from .mock_wger import mock_search

        search_fn = mock_search
        print("[MOCK DATA: canned wger results]\n")
    path = saved_plan.default_path()
    earlier = None
    if "--saved" in argv:
        earlier = saved_plan.load(path)
        if earlier is None:
            reason = saved_plan.ignored_reason(path)
            print(f"{reason}\n" if reason else "", end="")
            print(saved_plan.NO_SAVED_PLAN)
            return 1
    screen = Screen(cleared="--no-health-issues" in argv)  # one object between the question and its answer
    plan_args = (earlier.plan, earlier.saved_at) if earlier else (None, "")
    outcome = run_once(" ".join(args), search_fn, *plan_args, screen=screen)
    asked = 0
    while outcome.kind == "question" and outcome.reason == SCREEN_REASON and sys.stdin.isatty() and asked < 2:
        print(f"[question]\n\n{outcome.text}")
        try:
            answer = input("> ")
        except EOFError:
            break
        asked += 1
        outcome = run_once(answer, search_fn, *plan_args, screen=screen)
        print()
    print(f"[{outcome.kind}]\n")
    print(outcome.text)
    for failure in outcome.failures:
        print(f"  failed check: {failure}")
    if outcome.kind == "question" and outcome.reason == SCREEN_REASON:  # no terminal to answer in
        print("\n(Answer in a terminal window, or add --no-health-issues to say you have none.)")
    if "--trace" in argv:
        print("\n--- trace ---")
        print(format_trace(outcome.trace))
    if "--save" in argv:  # the checkpoint:  only a human's "yes" writes (homeset/saved_plan.py)
        print()
        if outcome.kind == "plan":
            saved_plan.offer_save(outcome.text, path)
        else:
            print("Not saved:  only a plan can be saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
