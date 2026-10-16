"""Try the save checkpoint with no API key and no network.

    python scripts/try_checkpoint.py

Runs the real checkpoint (homeset/saved_plan.py:offer_save) twice on two sample plans, in a temporary
folder that is deleted at the end (your real saved plan is never touched).  The first save shows
"(none)" for the old plan;  the second shows the first plan next to the second.  Type yes to save;
anything else, an empty line, or Ctrl-C saves nothing.  Run it in a terminal:  with no terminal the
checkpoint refuses to write, which is the point.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeset import saved_plan  # noqa: E402

SAMPLES = [c["saved_plan"] for c in json.loads((ROOT / "evals" / "cases" / "saved_plan.json").read_text())["cases"][:2]]


def main(ask=None, interactive=None, out=print) -> list[bool]:
    results = []
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "saved_plan.json"
        for number, plan in enumerate(SAMPLES, start=1):
            out(f"\n=== Save attempt {number} of {len(SAMPLES)} ===")
            results.append(saved_plan.offer_save(plan, path, ask=ask, interactive=interactive, out=out))
        loaded = saved_plan.load(path)
        out("\nWhat the file holds at the end:  " + (loaded.plan.splitlines()[1] if loaded else "nothing (no plan was saved)"))
    return results


if __name__ == "__main__":
    main()
