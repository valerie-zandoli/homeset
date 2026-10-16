"""The no-key checkpoint demo (scripts/try_checkpoint.py).  Added after a cold read on 2026-10-16 found that a
tester without an API key could not reach the checkpoint."""

import sys
from pathlib import Path

from homeset import saved_plan

sys.path.insert(0, str(Path(saved_plan.ROOT) / "scripts"))
import try_checkpoint  # noqa: E402


class Answers:
    def __init__(self, *replies):
        self.replies = list(replies)

    def __call__(self, _prompt):
        return self.replies.pop(0)


def test_the_demo_saves_on_yes_and_shows_none_for_the_first_old_plan():
    out = []
    assert try_checkpoint.main(Answers("yes", "no"), True, out.append) == [True, False]
    shown = "\n".join(out)
    assert "(none)" in shown and "Saved." in shown and "Not saved." in shown


def test_the_demo_with_no_terminal_writes_nothing():
    out = []
    assert try_checkpoint.main(Answers("yes", "yes"), False, out.append) == [False, False]
    assert "nothing (no plan was saved)" in "\n".join(out)
