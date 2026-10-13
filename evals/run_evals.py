"""Run eval cases through the agent and print a pass/fail table.

    python evals/run_evals.py evals/cases/controls.json
    python evals/run_evals.py evals/cases/eval_card.json --mock

A case passes here when the outcome KIND matches expect.kind ('plan', 'handoff',
'question', or 'error').  For plans the output checks have already run inside the
harness.  The NOTES in each case (counts, ranges, exact wording) are graded by two people
reading the saved run, the same way each time (PRD 3d).

Needs the API key in .env.  Results are saved to runs/ (ignored by git).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeset.agent import run_once  # noqa: E402
from homeset.mock_wger import mock_search  # noqa: E402
from homeset.wger import WgerUnavailable, search_exercises  # noqa: E402


def search_for(case: dict, mock: bool):
    inject = case.get("inject")
    if inject == "wger_unavailable":
        def broken(focus, equipment):
            raise WgerUnavailable("injected failure")
        return broken
    if inject == "empty_result":
        return lambda focus, equipment: {"focus": focus, "equipment_ids": [7], "groups": [
            {"count": 0, "examined": 0, "cut": False, "note": None, "no_english_name": 0, "exercises": [], "filter": "injected"}]}
    return mock_search if mock else search_exercises


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases_file")
    parser.add_argument("--mock", action="store_true", help="use canned wger data instead of the network")
    args = parser.parse_args()

    spec = json.loads(Path(args.cases_file).read_text())
    cases = spec.get("cases", [])
    if not cases:
        print(f"{args.cases_file} has no cases yet (owner: {spec.get('owner', 'unassigned')}).")
        return 1
    rows, passed = [], 0
    for case in cases:
        outcome = run_once(case["input"], search_for(case, args.mock))
        ok = outcome.kind == case["expect"]["kind"]
        passed += ok
        rows.append({"id": case["id"], "expected_kind": case["expect"]["kind"], "kind": outcome.kind, "pass": ok,
                     "failures": outcome.failures, "text": outcome.text})
        print(f"{'PASS' if ok else 'FAIL'}  {case['id']}  expected={case['expect']['kind']}  got={outcome.kind}")
    print(f"\n{passed} of {len(cases)} matched the expected kind.  Read the saved run to grade the notes.")
    out_dir = ROOT / "runs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{Path(args.cases_file).stem}.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"Saved {out.relative_to(ROOT)}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
