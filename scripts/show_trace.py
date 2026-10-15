"""Print the readable trace of saved eval rows.

    python scripts/show_trace.py runs/20261015-152550-requests_20.json a06
    python scripts/show_trace.py runs/20261015-152550-requests_20.json        # every row

Runs saved before 2026-10-15 hold the final text only and have no trace.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeset.trace import format_trace  # noqa: E402


def show(label: str, row: dict) -> None:
    trace = row.get("trace")
    if trace is None:
        print(f"{label}: no trace saved (the run predates trace logging)\n")
        return
    verdict = {True: "PASS", False: "FAIL"}.get(row.get("pass"), "-")
    print(f"=== {label}  kind={row.get('kind')}  {verdict}  retry fired: {row.get('retry_fired')}")
    print(format_trace(trace))
    print()


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python scripts/show_trace.py <run file> [case id]")
        return 2
    rows = json.loads(Path(argv[0]).read_text())
    wanted = argv[1] if len(argv) > 1 else None
    shown = 0
    for row in rows:
        if wanted and row.get("id") != wanted:
            continue
        shown += 1
        if "turns" in row:
            for n, turn in enumerate(row["turns"], 1):
                show(f"{row['id']} turn {n}", turn)
        else:
            show(row.get("id", "?"), row)
    if not shown:
        print(f"no row with id {wanted!r} in {argv[0]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
