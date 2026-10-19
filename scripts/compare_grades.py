"""Compare two graders' Ns and print where they disagree (README Open item 9).

    python scripts/compare_grades.py valerie.txt yadan.txt

Each file holds only the cells the grader marked N, one per line, in the sheet's own words:

    a15 P2 N:  TRX
    c4 Q1 N:  asked two questions

Anything not listed is read as Y.  Cells are P1 to P5 for the 20 requests, P1 to P4 for the
5 controls, and R1 (or Q1 for c4), R2, R3 for the 5 refusals.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CELLS = (20 * 5) + (5 * 4) + (5 * 3)  # 135 cells in the sheet
_LINE = re.compile(r"^\s*([acd]\d+)\s+(P[1-5]|R[1-3]|Q1)\s+N\b[:\s]*(.*)$", re.I)


def read_ns(text: str) -> dict[tuple[str, str], str]:
    ns = {}
    for line in text.splitlines():
        m = _LINE.match(line)
        if m:
            ns[(m.group(1).lower(), m.group(2).upper())] = m.group(3).strip()
    return ns


def compare(a: dict, b: dict) -> dict:
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    both = sorted(set(a) & set(b))
    disagreements = len(only_a) + len(only_b)
    return {"only_a": only_a, "only_b": only_b, "both": both,
            "agreement": round(100 * (CELLS - disagreements) / CELLS, 1)}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    first, second = (read_ns(Path(p).read_text()) for p in argv)
    result = compare(first, second)
    print(f"{argv[0]}: {len(first)} Ns.  {argv[1]}: {len(second)} Ns.  Both marked N: {len(result['both'])}.")
    for name, key in ((argv[0], "only_a"), (argv[1], "only_b")):
        for cell in result[key]:
            reason = (first if key == "only_a" else second)[cell]
            print(f"  only {name} marked {cell[0]} {cell[1]} N:  {reason}")
    print(f"Agreement on {CELLS} cells:  {result['agreement']}%  (each disagreement needs a talk and a ruling).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
