"""Command line:  python -m homeset "I have 20 minutes, a mat, and dumbbells.  Work on legs."

Add --mock to use canned wger data instead of the network (the model call still needs
the API key in .env).  Add --trace to print the step-by-step trace of the request.

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
from .trace import format_trace


USAGE = 'usage: python -m homeset "your request" [--mock] [--trace] [--save] [--saved]'
FLAGS = {"--mock", "--trace", "--save", "--saved"}


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
    if earlier:
        outcome = run_once(" ".join(args), search_fn, earlier.plan, earlier.saved_at)
    else:
        outcome = run_once(" ".join(args), search_fn)
    print(f"[{outcome.kind}]\n")
    print(outcome.text)
    for failure in outcome.failures:
        print(f"  failed check: {failure}")
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
