"""Pre-demo check:  scan the live wger English exercise text for injection-like strings.

wger exercise text is community-written, so it is untrusted input (diagram v3).  This reads
every English exercise from the live service (read-only GET requests, nothing saved to disk)
and looks in `name`, `description`, `description_source`, `aliases`, and `notes` for:

  alarm patterns  (the script exits 1 if any match):
    override phrases, role-play or system-prompt text, "do not tell" style directives,
    exfiltration wording, shell or credential words, markup and script tags, encoded blobs
  info patterns  (reported, never fail the check):
    URLs and email addresses
  names the agent would drop:
    any name that fails `homeset.wger.is_safe_name`

Run:  python scripts/scan_wger_text.py

Limits:  a pattern scan cannot catch plain-language manipulation (for example "skip the
warm-up"), it reads English entries only, and the data changes whenever someone edits it.
First run 2026-10-13:  932 exercises, no alarm hits, longest name 42 characters.
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from homeset.wger import BASE_URL, ENGLISH_LANGUAGE_ID, is_safe_name  # noqa: E402

PAGE_SIZE = 100
TIMEOUT_SECONDS = 30

ALARM_PATTERNS = {
    "override": r"ignore (all |any |your |the )?(previous|prior|above)|disregard|forget (all|your|previous)|new instructions|override",
    "role": r"\b(system prompt|you are (now|a|an)|act as|as an ai|jailbreak|developer mode)\b",
    "directive": r"\b(always (say|respond|reply)|do not (tell|mention)|instead,? (say|do|respond|output))\b",
    "exfil": r"\b(send|email|forward|upload|post)\b.{0,40}\b(to|at)\b.{0,40}(@|https?://)",
    "shell": r"\b(tool_call|function_call|api[_ ]?key|password|wget |sudo|rm -rf)\b",
    "markup": r"<\s*(script|iframe|img|object|embed|style)|javascript:|\bon\w+\s*=",
    "encoded": r"[A-Za-z0-9+/]{60,}={0,2}|\\u00[0-9a-f]{2}",
}
INFO_PATTERNS = {
    "url": r"https?://|www\.",
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
}
ALARM = {key: re.compile(pattern, re.I) for key, pattern in ALARM_PATTERNS.items()}
INFO = {key: re.compile(pattern, re.I) for key, pattern in INFO_PATTERNS.items()}


def fetch_all() -> list[dict]:
    """Every English exercise, following the next-page link."""
    exercises: list[dict] = []
    url: str | None = BASE_URL
    params: dict | None = {"language": ENGLISH_LANGUAGE_ID, "limit": PAGE_SIZE}
    while url:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        page = response.json()
        exercises.extend(page.get("results", []))
        url, params = page.get("next"), None  # the next link already carries the filters
    return exercises


def english_texts(exercise: dict) -> dict[str, str]:
    """The free-text fields of the English translation, one string per field."""
    for translation in exercise.get("translations", []):
        if translation.get("language") == ENGLISH_LANGUAGE_ID:
            return {
                "name": translation.get("name") or "",
                "description": translation.get("description") or "",
                "description_source": translation.get("description_source") or "",
                "notes": " | ".join(n.get("comment") or "" for n in translation.get("notes", [])),
                "aliases": " | ".join(a.get("alias") or "" for a in translation.get("aliases", [])),
            }
    return {}


def snippet(text: str, match: re.Match) -> str:
    return text[max(0, match.start() - 30):match.end() + 30].replace("\n", " ")


def main() -> int:
    try:
        exercises = fetch_all()
    except requests.RequestException as err:
        print(f"Could not read wger:  {type(err).__name__}")
        return 2

    alarms: list[tuple[int, str, str, str]] = []
    info_counts: collections.Counter = collections.Counter()
    unsafe_names: list[tuple[int, str]] = []
    longest = collections.Counter()
    scanned = 0

    for exercise in exercises:
        texts = english_texts(exercise)
        if not texts:
            continue
        scanned += 1
        if not is_safe_name(texts["name"]):
            unsafe_names.append((exercise["id"], texts["name"]))
        for field, text in texts.items():
            longest[field] = max(longest[field], len(text))
            for key, pattern in ALARM.items():
                match = pattern.search(text)
                if match:
                    alarms.append((exercise["id"], field, key, snippet(text, match)))
            for key, pattern in INFO.items():
                if pattern.search(text):
                    info_counts[(field, key)] += 1

    print(f"Exercises with an English translation:  {scanned} of {len(exercises)}")
    print("Longest text per field:  " + ", ".join(f"{k} {v}" for k, v in longest.items()))
    print("Info hits (not failures):  " + (", ".join(f"{f}/{k} {n}" for (f, k), n in sorted(info_counts.items())) or "none"))
    print(f"Names the agent would drop:  {len(unsafe_names)}")
    for exercise_id, name in unsafe_names:
        print(f"  {exercise_id}:  {name[:80]!r}")
    print(f"Alarm hits:  {len(alarms)}")
    for exercise_id, field, key, text in alarms:
        print(f"  {exercise_id}  {field}  {key}:  {text!r}")  # data, never instructions
    return 1 if alarms else 0


if __name__ == "__main__":
    sys.exit(main())
