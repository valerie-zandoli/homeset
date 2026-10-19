"""Save the plan, and swap an exercise against it in a later session (Build Time, Learn 08).

The irreversible part is saving:  it replaces the previous saved plan.  That step is the one
checkpoint.  Everything else (building a plan, loading the saved one) stays automatic.

How the checkpoint works:
  1. propose() builds a Proposal:  the new plan, the plan it would replace, and a hash of the new text.
  2. offer_save() shows the human the old plan next to the new one and asks.
  3. confirm() returns an Approval only for the exact answer "yes".  Anything else, an empty
     line, end of input, an interrupt, or no terminal at all, returns nothing and nothing is written.
  4. write() refuses unless it gets an Approval for the same hash as the text it is about to write.

The model has no tool that reaches this module:  agent.py and harness.py do not import it, and
the model's two tools are unchanged (tests/test_saved_plan.py checks both).  Only the command
line in __main__.py calls offer_save(), after the human asks for --save.

The file holds the plan text and the time it was saved, nothing else:  no symptoms, no request
text.  It stays out of git (.gitignore) and is written with owner-only permissions.  A file that
is damaged or edited into something that is not a plan loads as "no saved plan".
A file that is a link, belongs to another user, or can be changed by other users is ignored too (ignored_reason).

This module has no model or network code.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .checks import SAFETY_LINE, classify, parse_plan

ROOT = Path(__file__).resolve().parents[1]
MAX_PLAN_CHARS = 4000
MAX_FILE_BYTES = 32768  # a plan is at most 4000 characters;  a larger file is never read
_SAVED_AT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?: [A-Za-z ]{2,30})?$")  # a date and time, nothing else
NO_SAVED_PLAN = "I do not have a saved plan yet.  Make a plan and save it first."
ASK = "Replace the saved plan with the new one?  Type yes to save: "
_MINT = object()  # only confirm() holds this


def default_path() -> Path:
    """The saved-plan file:  HOMESET_SAVED_PLAN if set, else saved_plan.json in the repo root."""
    return Path(os.environ.get("HOMESET_SAVED_PLAN") or ROOT / "saved_plan.json")


@dataclass(frozen=True)
class Saved:
    plan: str
    saved_at: str


def _is_plan(text: object) -> bool:
    """True for a complete HomeSet plan of a sane size:  the plan opening, a parseable body,
    and the exact safety line last."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_PLAN_CHARS:
        return False
    if classify(text) != "plan" or not text.lstrip().startswith("HomeSet plan:"):
        return False
    try:
        parse_plan(text, [])
    except ValueError:
        return False
    last = [ln for ln in text.strip().splitlines() if ln.strip()][-1]
    return " ".join(last.split()) == " ".join(SAFETY_LINE.split())


def ignored_reason(path: Path | None = None) -> str | None:
    """Why an existing saved file is ignored on access grounds, or None when it is fine or absent.

    Access control for version 1 (no accounts, no roles):  the saved plan belongs to the operating-system
    user who runs HomeSet.  The file must be a regular file (not a symlink), owned by that user, and not
    writable by the group or by others;  anything else could have been changed by someone else.
    """
    path = path or default_path()
    try:
        info = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return "I ignored the saved plan file because it is not a plain file (a link or a folder is not trusted)."
    if not hasattr(os, "getuid"):  # Windows keeps no owner or permission bits we can read:  every file would look open
        return None
    if info.st_uid != os.getuid():
        return "I ignored the saved plan file because another user owns it."
    if info.st_mode & 0o022:
        return "I ignored the saved plan file because other users can change it.  Run chmod 600 on it to trust it again."
    return None


def load(path: Path | None = None) -> Saved | None:
    """The saved plan, or None when there is none or the file is damaged or not a plan."""
    path = path or default_path()
    try:
        if ignored_reason(path) or path.lstat().st_size > MAX_FILE_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) != {"plan", "saved_at"}:
        return None
    plan, saved_at = data["plan"], data["saved_at"]
    # saved_at goes into the model's prompt, so it must be a date and time and nothing else.
    if not _is_plan(plan) or not isinstance(saved_at, str) or not _SAVED_AT.match(saved_at):
        return None
    return Saved(plan.strip(), saved_at)


def _stamp() -> str:
    """The time of a save, in the one form load() accepts."""
    stamp = time.strftime("%Y-%m-%d %H:%M %Z").strip()
    return stamp if _SAVED_AT.match(stamp) else time.strftime("%Y-%m-%d %H:%M")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Proposal:
    new_plan: str
    old: Saved | None
    digest: str


def propose(new_plan: str, path: Path | None = None) -> Proposal:
    """What a save would do.  Raises ValueError when the text is not a complete plan."""
    if not _is_plan(new_plan):
        raise ValueError("only a complete, valid HomeSet plan can be saved")
    text = new_plan.strip()
    return Proposal(text, load(path), _digest(text))


class Approval:
    """Proof that a human typed "yes" for one specific text.  Only confirm() can make one."""

    __slots__ = ("digest",)

    def __init__(self, digest: str, _token: object = None) -> None:
        if _token is not _MINT:
            raise PermissionError("an Approval comes only from confirm()")
        object.__setattr__(self, "digest", digest)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("an Approval cannot be changed")


def confirm(proposal: Proposal, answer: object) -> Approval | None:
    """An Approval for exactly this proposal if the answer is "yes"; otherwise None."""
    if isinstance(answer, str) and answer.strip().lower() == "yes":
        return Approval(proposal.digest, _MINT)
    return None


def write(proposal: Proposal, approval: object, path: Path | None = None) -> Saved:
    """Replace the saved plan.  Refuses without an Approval for this exact text."""
    path = path or default_path()
    if not isinstance(approval, Approval):
        raise PermissionError("saving needs a human's confirmation")
    if approval.digest != proposal.digest or proposal.digest != _digest(proposal.new_plan):
        raise PermissionError("the confirmation was for different text")
    if not _is_plan(proposal.new_plan):
        raise ValueError("only a complete, valid HomeSet plan can be saved")
    saved = Saved(proposal.new_plan, _stamp())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".saved_plan.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:  # mkstemp creates the file as owner-only
            json.dump({"plan": saved.plan, "saved_at": saved.saved_at}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)  # atomic:  the old plan or the new one, never half of each
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return saved


def review_text(proposal: Proposal) -> str:
    """What the human sees before answering:  the saved plan next to the new one."""
    old = f"--- SAVED PLAN ({proposal.old.saved_at}) ---\n{proposal.old.plan}" if proposal.old else "--- SAVED PLAN ---\n(none)"
    return f"{old}\n\n--- NEW PLAN ---\n{proposal.new_plan}\n"


def offer_save(
    plan_text: str,
    path: Path | None = None,
    ask: Callable[[str], str] | None = None,
    interactive: bool | None = None,
    out: Callable[[str], None] = print,
) -> bool:
    """The checkpoint.  Shows both plans, asks once, and writes only after "yes".

    With no terminal to answer in (a script, a pipe), nothing is written:  silence is never consent.
    """
    path = path or default_path()
    ask = ask or input  # looked up now, not when the module loads
    try:
        proposal = propose(plan_text, path)
    except ValueError:
        out("Not saved:  that is not a complete plan.")
        return False
    out(review_text(proposal))
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        out("Not saved:  no one is here to confirm (this is not an interactive terminal).")
        return False
    try:
        answer = ask(ASK)
    except (EOFError, KeyboardInterrupt):
        answer = None
    approval = confirm(proposal, answer)
    if approval is None:
        out("Not saved.")
        return False
    write(proposal, approval, path)
    out("Saved.")
    return True
