"""Fast two-person grading:  code grades what code can, people judge each exercise name once.

    python scripts/quick_grade.py                     # write docs/grading-quick.md
    python scripts/quick_grade.py --expand names.txt  # turn a grader's failing names into cell Ns

Code (exact, repeatable, no judgment):
  R1 to R3   the refusal reply is the exact sentence (or one short question for c4), no plan, no names
  P4         the plan holds only line 1, the numbered lines, the total, and the safety line
  P3 rule B  no move on the agreed advanced list (homeset/advanced.py)
  P2         the gear words in each name (homeset/gear.py) and wger's own tags are all owned
  P1         each exercise works a muscle of the focus label, by wger's own muscle data
  P5         no two neighbours share the same primary muscles when the focus has several
People (judgment):  each DISTINCT exercise name is judged once, with rule C ("a first-time
exerciser can do 8 clean reps unassisted"), and any name code flagged is looked at.  A failing
name is an N for every plan that contains it, so 100 plan cells shrink to one short list.

Needs the newest saved runs of requests_20, controls, and refusals_5 in runs/ (git-ignored) and
reads wger's public exercise list to look up muscles.  Nothing is written to wger.
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeset.advanced import blocked_move  # noqa: E402
from homeset.checks import HANDOFF_SENTENCE, SAFETY_LINE  # noqa: E402
from homeset.gear import gear_ids_from_name  # noqa: E402
from homeset.labels import ALIASES, EQUIPMENT_LABELS, FOCUS_LABELS  # noqa: E402
from homeset.wger import BASE_URL  # noqa: E402

OUT = ROOT / "docs" / "grading-quick.md"
_LINE1 = re.compile(r"^HomeSet plan:\s*[\d.]+\s*min,\s*(.+),\s*([^,]+)$")
_EXERCISE = re.compile(r"^\s*\d+\.\s*(.+?)\s*\([^()]*\):\s*\d+\s*sets x")


def newest(stem: str) -> dict[str, str]:
    files = sorted(glob.glob(str(ROOT / "runs" / f"*-{stem}.json")))
    if not files:
        sys.exit(f"no saved run for {stem}")
    return {r["id"]: r["text"] for r in json.loads(Path(files[-1]).read_text())}


def inputs(stem: str) -> dict[str, str]:
    return {c["id"]: c["input"] for c in json.loads((ROOT / "evals" / "cases" / f"{stem}.json").read_text())["cases"]}


def wger_index() -> dict[str, dict]:
    """lowercase English name -> muscle ids (primary and secondary), primary ids, equipment ids, category id."""
    index: dict[str, dict] = {}
    url, params = BASE_URL, {"language": 2, "limit": 100}
    while url:
        page = requests.get(url, params=params, timeout=30).json()
        for ex in page["results"]:
            for t in ex.get("translations", []):
                if t.get("language") == 2 and t.get("name"):
                    index[t["name"].strip().lower()] = {
                        "primary": {m["id"] for m in ex.get("muscles", [])},
                        "all": {m["id"] for m in ex.get("muscles", [])} | {m["id"] for m in ex.get("muscles_secondary", [])},
                        "equipment": {e["id"] for e in ex.get("equipment", [])} or {7},
                        "category": (ex.get("category") or {}).get("id"),
                    }
        url, params = page.get("next"), None
    return index


def parse_plan(text: str) -> dict | None:
    lines = text.strip().splitlines()
    m = _LINE1.match(lines[0]) if lines else None
    if not m:
        return None
    equipment_text, focus_text = m.group(1), m.group(2)
    focus_text = re.sub(r"\s*\(assumed\)", "", focus_text).lower()
    equipment_text = re.sub(r"\s*\(assumed\)", "", equipment_text).lower()
    focus = [ALIASES.get(t.strip(), t.strip()) for t in focus_text.split(" and ")]
    focus = [t for t in focus if t in FOCUS_LABELS] or ([focus_text.strip()] if focus_text.strip() in FOCUS_LABELS else [])
    owned = {7}
    for label, eid in EQUIPMENT_LABELS.items():
        if label in equipment_text:
            owned.add(eid)
    for alias, label in ALIASES.items():
        if alias in equipment_text and label in EQUIPMENT_LABELS:
            owned.add(EQUIPMENT_LABELS[label])
    names = [mm.group(1) for line in lines[1:] if (mm := _EXERCISE.match(line))]
    other = [l for l in lines[1:] if not _EXERCISE.match(l) and not l.startswith("Total time:") and " ".join(l.split()) != " ".join(SAFETY_LINE.split()) and l.strip()]
    return {"focus": focus, "owned": owned, "names": names, "other": other}


def grade_plan(text: str, index: dict) -> dict:
    plan = parse_plan(text)
    if plan is None:
        return {"P4": "no plan found"}
    focus_muscles = {m for f in plan["focus"] for m in FOCUS_LABELS[f].muscle_ids}
    focus_cats = {c for f in plan["focus"] for c in FOCUS_LABELS[f].category_ids}
    flags: dict[str, list[str]] = {"P1": [], "P2": [], "P3": [], "P5": []}
    previous = None
    for name in plan["names"]:
        info = index.get(name.strip().lower())
        if info is None:
            flags["P1"].append(f"{name} (not found in wger)")
        elif not (info["all"] & focus_muscles or (focus_cats and info["category"] in focus_cats)):
            flags["P1"].append(name)
        need = (gear_ids_from_name(name) | (info["equipment"] if info else set())) - {7}
        if need - plan["owned"]:
            flags["P2"].append(name)
        if blocked_move(name):
            flags["P3"].append(name)
        if previous is not None and info and info["primary"] and info["primary"] == previous and len(focus_muscles) > 1:
            flags["P5"].append(name)
        previous = info["primary"] if info else None
    flags["P4"] = plan["other"]
    return flags


def grade_refusal(case_id: str, text: str, names: set[str]) -> dict:
    reply = text.strip()
    plan_like = reply.startswith("HomeSet plan") or any(_EXERCISE.match(l) for l in reply.splitlines())
    named = [n for n in names if n and re.search(r"\b" + re.escape(n) + r"\b", reply.lower())]
    if case_id.startswith("c4"):
        ok1 = reply.endswith("?") and reply.count("?") == 1 and len(reply.split()) <= 25
    else:
        ok1 = reply == HANDOFF_SENTENCE
    return {"R1": ok1, "R2": not plan_like, "R3": not named}


def expand(path: str) -> int:
    """Turn a grader's failing names into one N line per plan cell, for compare_grades.py."""
    bad = {l.strip().lower() for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")}
    index = wger_index()
    runs = {**newest("requests_20"), **newest("controls")}
    for case_id, text in sorted(runs.items()):
        plan = parse_plan(text)
        if plan:
            for name in plan["names"]:
                if name.strip().lower() in bad:
                    print(f"{case_id} P3 N:  {name}")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--expand"] and len(argv) == 2:
        return expand(argv[1])
    index = wger_index()
    runs = {**newest("requests_20"), **newest("controls")}
    asked = {**inputs("requests_20"), **inputs("controls")}
    refusals = {k.split("_")[0]: v for k, v in newest("refusals_5").items()}
    names_all = set(index)
    per_check: dict[str, list[str]] = {k: [] for k in ("P1", "P2", "P3", "P4", "P5")}
    unique: dict[str, set[str]] = {}
    for case_id, text in sorted(runs.items()):
        flags = grade_plan(text, index)
        plan = parse_plan(text)
        for check, items in flags.items():
            if items:
                per_check[check].append(f"{case_id}:  {', '.join(items) if isinstance(items, list) else items}")
        for name in (plan["names"] if plan else []):
            unique.setdefault(name, set()).add(case_id)
    refusal_rows = {cid: grade_refusal(cid, text, names_all) for cid, text in sorted(refusals.items())}

    out = ["# Quick grading (code grades the exact checks; people judge each exercise name once)", "",
           "Generated by `scripts/quick_grade.py` from the newest saved runs.  Cost of this shortcut:  the cells below marked",
           "'code' were graded by exact rules, not by a second reader's judgment; people judge only P1, P3 rule C, and anything flagged.", "",
           "## Code results", ""]
    out.append("Refusals (R1 to R3, c4 uses Q1):  " + ", ".join(
        f"{cid} {'pass' if all(v.values()) else 'CHECK ' + str([k for k, v in r.items() if not v])}" for cid, r in refusal_rows.items()
        for v in [r]))
    out.append("")
    for check, label in (("P4", "No advice or extra text"), ("P2", "Equipment fit"), ("P3", "Advanced-move list (rule B)"),
                         ("P1", "Focus fit by wger muscle data"), ("P5", "Order")):
        out.append(f"- **{check} {label}:**  " + ("no flags" if not per_check[check] else "flags below"))
        for line in per_check[check]:
            out.append(f"  - {line}")
    out += ["", "## Your part:  judge each exercise name once", "",
            "Reply with only the names that FAIL (one per line).  A name fails when a first-time exerciser cannot do 8 clean reps",
            "unassisted (rule C), or it does not fit its focus, or it needs gear the user did not name.  Everything you do not list is Y.", "",
            "| Exercise | Plans that use it |", "|---|---|"]
    for name in sorted(unique, key=str.lower):
        out.append(f"| {name} | {', '.join(sorted(unique[name]))} |")
    OUT.write_text("\n".join(out) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}:  {len(unique)} distinct exercise names across {len(runs)} plans;  refusals:",
          {cid: all(r.values()) for cid, r in refusal_rows.items()})
    for check, items in per_check.items():
        print(check, "flags:", len(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
