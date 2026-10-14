"""wger client: the one read-only tool that reaches outside our code.

What the PRD (Section 3a) and diagram v3 require of this module:
  - GET https://wger.de/api/v2/exerciseinfo/ with language=2, muscles / category, equipment
  - repeat a filter once per value (a comma-separated list returns an error)
  - 20 results per page with a total count and a next-page link: follow the link and mark
    any list that was cut ("showing 20 of 104")
  - 10 second timeout, one retry; HTTP 429 counts as a tool failure after the one retry
  - language=2 still returns every translation, so read the translation whose language is 2
  - the equipment filter matches ANY listed item, so an exercise that also needs gear the
    user lacks (a bench) is dropped here
  - only read-only GET requests; nothing is written

Added 2026-10-14 (Failure Modes lesson; in PRD sections 3a, 3c, and 3d):
  - a 200 response must carry an integer count and a list of results; anything else is a
    failure (WgerUnavailable), never an empty list, because "no exercises" would tell the
    user a fact the code does not know
  - when half or more of the examined results have no readable English name, the answer is a
    failure:  that is a changed response shape, not an empty database
  - one search call may take at most 30 seconds in total, retries included
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

import requests

from .gear import gear_ids_from_name
from .labels import BODYWEIGHT_ID, equipment_ids, focus_filters

BASE_URL = "https://wger.de/api/v2/exerciseinfo/"
ENGLISH_LANGUAGE_ID = 2
PAGE_SIZE = 20
MAX_RESULTS_PER_SEARCH = 40  # two pages per muscle; the cut is marked when more exist
TIMEOUT_SECONDS = 10
RETRY_WAIT_SECONDS = 1.0
MAX_SECONDS_PER_SEARCH = 30  # all muscles, pages, and retries; a request already sent can still run to its 10 s timeout
MIN_EXAMINED_FOR_SHAPE_CHECK = 5
MAX_UNREADABLE_SHARE = 0.5  # live baseline 2026-10-14:  0 of 1,013 examined across the 12 focus labels


MAX_NAME_LENGTH = 45  # the longest English name on wger is 42 (scan 2026-10-13)
_SENTENCE_BREAK = re.compile(r"[A-Za-z]{2,}[.!?]\s+[A-Z]")  # "Up.  Ignore", not "w. Rotation"


MAX_NAME_WORDS = 8  # the longest real name has 7 words (932 English names, scan 2026-10-14)
# Letters (accents included), digits, spaces, and the punctuation that real names use:
# ( ) - , / : ' ’ | + & – ° > and a dot.  No double quotes, angle-bracket tags, semicolons,
# at-signs, or backticks, and no dot between two word characters, so markup, URLs, e-mail
# addresses, and shell text cannot sit inside a name.
_ALLOWED_NAME = re.compile(r"^[^\W_](?:[^\W_]|[ ()\-,/:'’|+&–°>.])*$")
_DOT_BETWEEN_WORDS = re.compile(r"\w\.\w")  # example.com, a.b; "Curls w. Rotation" is fine
# Instruction, advert, and role-play words.  None of the 932 real names contains one.
_DENIED_WORDS = re.compile(
    r"\b(ignore|disregard|forget|instruction|instructions|prompt|system|override|tell|ask|say|"
    r"buy|purchase|visit|click|http|https|www|doctor|physician|skip|stop|never|always|must|should|"
    r"user|assistant|supplement|discount|promo|warning|warnings|advice|medical|safety)\b",
    re.IGNORECASE,
)


def is_safe_name(name: str) -> bool:
    """A name is a short label, not a sentence or an instruction.  Exercise names are
    community-edited and always reach the model and then the user, so a name is dropped
    before the model sees it when it is long, has a line break or a sentence break, has more
    than 8 words, uses a character no real name uses, or contains an instruction or advert
    word.  This does not stop every injection (plain wording with other words gets
    through); it removes the obvious ones.  The scan script reports any real name this
    drops, and tests/fixtures/wger_english_names.json must stay at zero drops."""
    return (
        0 < len(name) <= MAX_NAME_LENGTH
        and "\n" not in name
        and len(name.split()) <= MAX_NAME_WORDS
        and bool(_ALLOWED_NAME.match(name))
        and not _SENTENCE_BREAK.search(name)
        and not _DOT_BETWEEN_WORDS.search(name)
        and not _DENIED_WORDS.search(name)
    )


class WgerUnavailable(RuntimeError):
    """wger could not be reached (or kept refusing) after one retry."""


Getter = Callable[..., Any]


def _default_get(url: str, params: list[tuple[str, Any]] | None, timeout: int) -> Any:
    return requests.get(url, params=params, timeout=timeout)


def _read_page(response: Any) -> tuple[dict | None, str]:
    """The page, or None and the reason.  A 200 whose body is not a page is a failure:  read
    as an empty list, it would tell the user that wger has no exercises.  The reason is
    fixed wording, never text from the response."""
    try:
        data = response.json()
    except ValueError:
        return None, "the response was not JSON"
    if not isinstance(data, dict):
        return None, "the response was not a JSON object"
    count, results, next_url = data.get("count"), data.get("results"), data.get("next")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return None, "the response had no integer count"
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        return None, "the response had no list of results"
    if next_url is not None and not isinstance(next_url, str):
        return None, "the next link was not text"
    return data, ""


def _fetch_json(url: str, params: list[tuple[str, Any]] | None, get: Getter, sleep=time.sleep) -> dict:
    """GET with a timeout and one retry on timeout, connection error, HTTP 429, 5xx, or a 200
    whose body is not a results page."""
    last_error = "unknown error"
    for attempt in range(2):
        try:
            response = get(url, params, TIMEOUT_SECONDS)
        except (requests.Timeout, requests.ConnectionError) as err:
            last_error = f"{type(err).__name__}"
        else:
            if response.status_code == 200:
                page, problem = _read_page(response)
                if page is not None:
                    return page
                last_error = problem  # a healthy status with an unusable body is a failure
            else:
                last_error = f"HTTP {response.status_code}"
                if response.status_code != 429 and response.status_code < 500:
                    break  # a 4xx that is not 429 will not improve on retry
                wait = response.headers.get("Retry-After") if hasattr(response, "headers") else None
                if wait and str(wait).isdigit():
                    sleep(min(int(wait), 5))
                    continue
        if attempt == 0:
            sleep(RETRY_WAIT_SECONDS)
    raise WgerUnavailable(last_error)


def _english_translation(raw: dict) -> dict | None:
    """The English translation with a name, or None.  A translations field of any other
    shape counts as no translation."""
    translations = raw.get("translations")
    if not isinstance(translations, list):
        return None
    return next(
        (
            t
            for t in translations
            if isinstance(t, dict) and t.get("language") == ENGLISH_LANGUAGE_ID and t.get("name")
        ),
        None,
    )


def clean_exercise(raw: dict, include_description: bool = False) -> dict | None:
    """One clean record per exercise, or None when it has no English translation.

    Keeps English name, equipment, muscles, and category.  The free-text description is
    dropped unless asked for:  it is community-edited text and a way for injected
    instructions to reach the model (a proposal in diagram v3, not yet in the PRD).
    """
    english = _english_translation(raw)
    if english is None or not is_safe_name(english["name"].strip()):
        return None
    equipment = raw.get("equipment") or []
    record = {
        "id": raw.get("id"),
        "name": english["name"].strip(),
        "equipment": [e.get("name", "") for e in equipment] or ["none (bodyweight exercise)"],
        # The tag is community data and can disagree with the name ("Biceps with TRX" is tagged
        # bodyweight), so the gear the name implies counts too (homeset/gear.py).
        "equipment_ids": sorted(
            ({e["id"] for e in equipment if "id" in e} or {BODYWEIGHT_ID}) | gear_ids_from_name(english["name"])
        ),
        "muscles": [m.get("name_en") or m.get("name", "") for m in raw.get("muscles", [])],
        "category": (raw.get("category") or {}).get("name", ""),
    }
    if include_description:
        record["description"] = english.get("description", "")
    return record


def _search_one(
    filter_name: str,
    filter_id: int,
    owned_ids: tuple[int, ...],
    get: Getter,
    sleep=time.sleep,
    include_description: bool = False,
) -> dict:
    params: list[tuple[str, Any]] = [("language", ENGLISH_LANGUAGE_ID), ("limit", PAGE_SIZE), (filter_name, filter_id)]
    params += [("equipment", e) for e in owned_ids]  # repeated once per value
    url: str | None = BASE_URL
    count, seen, kept, skipped, unreadable = 0, 0, [], 0, 0
    while url and seen < MAX_RESULTS_PER_SEARCH:
        page = _fetch_json(url, params if url == BASE_URL else None, get, sleep)
        count = page["count"]
        for raw in page["results"]:
            seen += 1
            try:
                readable = _english_translation(raw) is not None
                record = clean_exercise(raw, include_description) if readable else None
            except (AttributeError, TypeError, KeyError, ValueError):
                readable, record = False, None  # a record of an unexpected shape is counted, not ignored
            if not readable:
                unreadable += 1
            if record is None:
                skipped += 1
            elif set(record["equipment_ids"]) <= set(owned_ids):  # drop gear the user lacks
                kept.append(record)
        url = page["next"] if "next" in page else None
        if url and not url.startswith(BASE_URL):
            url = None  # a next link must stay on wger; a response cannot send us elsewhere
    if seen >= MIN_EXAMINED_FOR_SHAPE_CHECK and unreadable / seen >= MAX_UNREADABLE_SHARE:
        # Many results with no readable English name look like a changed response shape, not an
        # empty database.  An unsafe name that the filter drops is not counted here.
        raise WgerUnavailable(f"{unreadable} of {seen} results had no readable English name")
    cut = count > seen
    return {
        "count": count,
        "examined": seen,
        "cut": cut,
        "note": f"showing {seen} of {count}" if cut else None,
        "skipped_names": skipped,  # no English name, or a name that is not a short label
        "unreadable": unreadable,  # no readable English name (a shape problem, not a filtered name)
        "exercises": kept,
    }


def search_exercises(
    focus: str,
    equipment: list[str],
    get: Getter = _default_get,
    sleep=time.sleep,
    include_description: bool = False,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """The tool the model calls.  Labels in, grouped clean exercises out.

    focus: one FOCUS label (or alias).  equipment: EQUIPMENT labels (or aliases).
    Runs one wger search per muscle in the focus label (never more than five).
    Raises UnknownLabel for a label outside the fixed lists, WgerUnavailable for wger failures
    (including a response that is not a results page and a call that outlasts the deadline).
    """
    f = focus_filters(focus)
    owned = equipment_ids(equipment)
    searches = [("muscles", m) for m in f.muscle_ids] or [("category", c) for c in f.category_ids]
    started = clock()

    def get_within_deadline(url: str, params: list[tuple[str, Any]] | None, timeout: int) -> Any:
        if clock() - started > MAX_SECONDS_PER_SEARCH:
            raise WgerUnavailable(f"the search took longer than {MAX_SECONDS_PER_SEARCH} seconds")
        return get(url, params, timeout)

    groups, used = [], set()
    for filter_name, filter_id in searches:
        result = _search_one(filter_name, filter_id, owned, get_within_deadline, sleep, include_description)
        unique = []
        for ex in result["exercises"]:  # an exercise can match several muscles; list it once
            if ex["id"] not in used:
                used.add(ex["id"])
                unique.append(ex)
        result["exercises"] = unique
        result["filter"] = f"{filter_name}={filter_id}"
        groups.append(result)
    return {"focus": f.label, "equipment_ids": list(owned), "groups": groups}
