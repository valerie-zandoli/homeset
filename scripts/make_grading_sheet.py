"""Refresh docs/grading-sheet.md from the newest saved runs, so both graders read what ships.

    python scripts/make_grading_sheet.py

Keeps every rule, legend, and heading in the sheet; replaces only the Reply, Line 1, Plan,
and Total cells of each case row with the newest saved run of requests_20, controls, and
refusals_5, and clears the check boxes.  Runs are read from runs/ (git-ignored).
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "docs" / "grading-sheet.md"
BOX = "☐"

_EXERCISE = re.compile(r"^\s*\d+\.\s*(.+?)\s*\([^()]*\):\s*(\d+)\s*sets x\s*(\d+)\s*reps,\s*rest\s*(\d+)\s*s", re.I)


def newest(stem: str) -> tuple[str, dict[str, str]]:
    files = sorted(glob.glob(str(ROOT / "runs" / f"*-{stem}.json")))
    if not files:
        sys.exit(f"no saved run for {stem}; run evals/run_evals.py evals/cases/{stem}.json first")
    rows = json.loads(Path(files[-1]).read_text())
    return Path(files[-1]).name, {r["id"]: r["text"] for r in rows}


def plan_cells(text: str) -> tuple[str, str, str]:
    """(line 1 without the prefix, 'Name SxR/T; ...', total minutes) from a plan's text."""
    line1 = re.sub(r"^HomeSet plan:\s*", "", text.splitlines()[0]).strip()
    exercises = []
    for line in text.splitlines():
        m = _EXERCISE.match(line)
        if m:
            exercises.append(f"{m.group(1)} {m.group(2)}x{m.group(3)}/{m.group(4)}")
    total = re.search(r"Total time:\s*([\d.]+)", text)
    return line1, "; ".join(exercises), (total.group(1) if total else "?")


def boxes(n: int) -> str:
    return " | ".join([BOX] * n)


def main() -> int:
    lines = SHEET.read_text().splitlines()
    names = {}
    texts = {}
    for stem in ("requests_20", "controls", "refusals_5"):
        names[stem], run = newest(stem)
        texts.update(run)
        texts.update({k.split("_")[0]: v for k, v in run.items() if re.match(r"c\d+_", k)})  # c1_direct_override -> c1
    out = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("| ") else []
        case_id = cells[0] if cells else ""
        if case_id in texts and re.fullmatch(r"[acd]\d+", case_id):
            text = texts[case_id]
            if case_id.startswith("c"):  # refusal row: ID, input, reply, R1 or Q1, R2, R3
                reply = text.strip().replace("\n", " ")  # keep the spacing:  R1 asks for the exact sentence
                out.append(f"| {case_id} | {cells[1]} | {reply} | {boxes(3)} |")
            elif case_id.startswith("d"):  # control row: ID, input, line 1, plan, P1..P4
                line1, plan, _ = plan_cells(text)
                out.append(f"| {case_id} | {cells[1]} | {line1} | {plan} | {boxes(4)} |")
            else:  # request row: ID, request, line 1, plan, total, P1..P5
                line1, plan, total = plan_cells(text)
                out.append(f"| {case_id} | {cells[1]} | {line1} | {plan} | {total} | {boxes(5)} |")
        elif line.startswith("Source runs"):
            out.append("Source runs (saved, git-ignored): " + ", ".join(f"`runs/{n}`" for n in names.values()) + ".")
        else:
            out.append(line)
    SHEET.write_text("\n".join(out) + "\n")
    print("Refreshed", SHEET.relative_to(ROOT), "from", ", ".join(names.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
