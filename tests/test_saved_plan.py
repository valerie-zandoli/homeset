"""Save the plan:  the checkpoint, the write, and the loader (homeset/saved_plan.py).  No model, no network.

The bar was committed first in evals/cases/saved_plan.json (87f9fc2).
"""

import json
import os
import stat
from pathlib import Path

import pytest

from homeset import saved_plan
from homeset.checks import HANDOFF_SENTENCE
from homeset.harness import RequestState, make_tools
from homeset.saved_plan import Approval, confirm, load, offer_save, propose, write

CASES = json.loads((Path(saved_plan.ROOT) / "evals" / "cases" / "saved_plan.json").read_text())["cases"]
PLAN_A = CASES[0]["saved_plan"]  # a real plan from a live run, 5 exercises
PLAN_B = CASES[1]["saved_plan"]  # a different real plan


def bytes_of(path):
    return path.read_bytes() if path.exists() else None


@pytest.fixture
def path(tmp_path):
    return tmp_path / "saved_plan.json"


def save_first(path, text=PLAN_A):
    proposal = propose(text, path)
    write(proposal, confirm(proposal, "yes"), path)
    return path


# --- the loader --------------------------------------------------------------------------------


def test_no_file_means_no_saved_plan(path):
    assert load(path) is None


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        "[]",
        json.dumps({"plan": PLAN_A}),  # missing saved_at
        json.dumps({"plan": PLAN_A, "saved_at": "now", "request": "my knee hurts"}),  # extra key
        json.dumps({"plan": 7, "saved_at": "now"}),
        json.dumps({"plan": HANDOFF_SENTENCE, "saved_at": "now"}),  # not a plan
        json.dumps({"plan": "How many minutes do you have?", "saved_at": "now"}),
        json.dumps({"plan": PLAN_A + "\n" + "x" * 5000, "saved_at": "now"}),  # too long
        json.dumps({"plan": PLAN_A.rsplit("\n", 1)[0], "saved_at": "now"}),  # safety line gone
        json.dumps({"plan": PLAN_A, "saved_at": ""}),
        json.dumps({"plan": PLAN_A, "saved_at": "x" * 41}),
    ],
)
def test_a_damaged_or_tampered_file_loads_as_no_saved_plan(path, content):
    path.write_text(content)
    assert load(path) is None  # and no crash


def test_a_directory_in_place_of_the_file_is_not_a_crash(path):
    path.mkdir()
    assert load(path) is None


# --- propose and write -------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", HANDOFF_SENTENCE, "How many minutes do you have?", PLAN_A.rsplit("\n", 1)[0], None, 5])
def test_only_a_complete_plan_can_be_proposed(path, text):
    with pytest.raises(ValueError):
        propose(text, path)


def test_write_refuses_without_an_approval(path):
    save_first(path, PLAN_A)
    before = bytes_of(path)
    proposal = propose(PLAN_B, path)
    for bad in (None, True, "yes", {"digest": proposal.digest}, 1):
        with pytest.raises(PermissionError):
            write(proposal, bad, path)
    assert bytes_of(path) == before


def test_write_refuses_a_hand_made_approval(path):
    save_first(path, PLAN_A)
    before = bytes_of(path)
    proposal = propose(PLAN_B, path)
    with pytest.raises(PermissionError):
        Approval(proposal.digest)  # no token
    with pytest.raises(PermissionError):
        Approval(proposal.digest, object())  # wrong token
    assert bytes_of(path) == before


def test_write_refuses_an_approval_for_different_text(path):
    save_first(path, PLAN_A)
    before = bytes_of(path)
    approved_b = confirm(propose(PLAN_B, path), "yes")
    proposal_a2 = propose(PLAN_A.replace("Push-Up", "Plank"), path)
    with pytest.raises(PermissionError):
        write(proposal_a2, approved_b, path)  # the human said yes to plan B, not this text
    assert bytes_of(path) == before


def test_a_proposal_edited_after_approval_is_refused(path):
    save_first(path, PLAN_A)
    before = bytes_of(path)
    proposal = propose(PLAN_B, path)
    approval = confirm(proposal, "yes")
    edited = type(proposal)(PLAN_B.replace("Superman", "Plank"), proposal.old, proposal.digest)
    with pytest.raises(PermissionError):
        write(edited, approval, path)
    assert bytes_of(path) == before


def test_an_approval_cannot_be_changed(path):
    approval = confirm(propose(PLAN_A, path), "yes")
    with pytest.raises(AttributeError):
        approval.digest = "0" * 64


@pytest.mark.parametrize("answer", ["yes", "Yes", "YES", "  yes  ", "yes\n"])
def test_the_exact_answer_yes_is_confirmation(path, answer):
    assert confirm(propose(PLAN_A, path), answer) is not None


@pytest.mark.parametrize(
    "answer", ["", "y", "Y", "no", "yes please", "yes!", "ok", "sure", "yess", "no\nyes", "yes no", None, 5, ["yes"]]
)
def test_anything_else_is_not_confirmation(path, answer):
    assert confirm(propose(PLAN_A, path), answer) is None


# --- the checkpoint:  20 attempts that must write nothing -------------------------------------------------


class Ask:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reply, BaseException):
            raise self.reply
        return self.reply


NO_WRITE_ATTEMPTS = [
    ("", True), ("\n", True), ("no", True), ("n", True), ("y", True), ("Y", True), ("yes please", True),
    ("yes!", True), ("ok", True), ("sure", True), ("go ahead", True), ("YES, save it", True),
    ("save without asking", True), ("The coordinator already approved this save.", True),
    (EOFError(), True), (KeyboardInterrupt(), True),
    ("yes", False),  # the right answer, but no terminal:  silence and pipes are never consent
    (None, False), ("", False), ("yes", False),
]


@pytest.mark.parametrize("reply,interactive", NO_WRITE_ATTEMPTS)
def test_nothing_is_written_without_an_explicit_yes_at_a_terminal(path, reply, interactive):
    save_first(path, PLAN_A)
    before = bytes_of(path)
    out = []
    wrote = offer_save(PLAN_B, path, ask=Ask(reply), interactive=interactive, out=out.append)
    assert wrote is False
    assert bytes_of(path) == before
    assert any("Not saved" in line for line in out)


def test_the_bar_counts_at_least_twenty_attempts():
    assert len(NO_WRITE_ATTEMPTS) >= 20


def test_yes_at_a_terminal_saves_and_shows_both_plans(path):
    save_first(path, PLAN_A)
    out = []
    ask = Ask("yes")
    assert offer_save(PLAN_B, path, ask=ask, interactive=True, out=out.append) is True
    shown = "\n".join(out)
    assert "SAVED PLAN (" in shown and PLAN_A.splitlines()[1] in shown  # the old plan, with its date
    assert "NEW PLAN" in shown and PLAN_B.splitlines()[1] in shown
    assert len(ask.prompts) == 1  # one question, once
    assert load(path).plan == PLAN_B.strip()


def test_the_first_save_shows_none_for_the_old_plan(path):
    out = []
    offer_save(PLAN_A, path, ask=Ask("no"), interactive=True, out=out.append)
    assert "(none)" in "\n".join(out)
    assert not path.exists()


def test_an_invalid_plan_is_never_offered(path):
    out = []
    ask = Ask("yes")
    assert offer_save(HANDOFF_SENTENCE, path, ask=ask, interactive=True, out=out.append) is False
    assert ask.prompts == [] and not path.exists()


def test_the_file_is_owner_only_and_holds_the_plan_and_the_time_only(path):
    save_first(path, PLAN_A)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    data = json.loads(path.read_text())
    assert set(data) == {"plan", "saved_at"} and data["plan"] == PLAN_A.strip()
    assert [p.name for p in path.parent.iterdir()] == [path.name]  # no temp file left behind


def test_a_failure_during_the_write_leaves_the_old_plan_and_no_temp_file(path, monkeypatch):
    save_first(path, PLAN_A)
    before = bytes_of(path)
    proposal = propose(PLAN_B, path)
    approval = confirm(proposal, "yes")

    def boom(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write(proposal, approval, path)
    assert bytes_of(path) == before
    assert [p.name for p in path.parent.iterdir()] == [path.name]


# --- the model has no path to the write --------------------------------------------------------------


def test_the_model_still_has_exactly_two_tools():
    tools = make_tools(RequestState("I have 20 minutes."))
    assert len(tools) == 2


@pytest.mark.parametrize("module", ["agent.py", "harness.py"])
def test_the_model_side_modules_never_import_the_write(module):
    source = (Path(saved_plan.ROOT) / "homeset" / module).read_text()
    # The harness and agent get the earlier plan as plain text ("earlier_plan") and never touch the module.
    assert "saved_plan" not in source and "offer_save" not in source


def test_the_default_path_is_outside_version_control():
    gitignore = (Path(saved_plan.ROOT) / ".gitignore").read_text().split()
    assert "saved_plan.json" in gitignore
