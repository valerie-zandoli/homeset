"""The health question on the two surfaces that talk to a person:  the command line and the chat page's server.
No model and no network;  a scripted agent stands in (see tests/test_health_screen.py for the rule itself)."""

import json
from pathlib import Path

from homeset import __main__ as cli
from homeset import agent as agent_module
from homeset import web
from homeset.checks import HANDOFF_SENTENCE
from homeset.messages import SCREEN_QUESTION

from test_vague import ScriptedAgent

ROOT = Path(__file__).resolve().parents[1]
REQ = "I have 15 minutes and a mat.  Legs."
ASK_MINUTES = "How many minutes do you have?"  # a scripted model reply that is not a plan


# --- the command line --------------------------------------------------------------------------------------

def patch_agent(monkeypatch, replies):
    agent = ScriptedAgent(list(replies))
    monkeypatch.setattr(agent_module, "build_agent", lambda state, search_fn=None: agent)
    return agent


def test_the_command_line_asks_the_question_and_reads_the_answer_at_a_terminal(monkeypatch, capsys):
    agent = patch_agent(monkeypatch, [ASK_MINUTES])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    assert cli.main([REQ]) == 0
    out = capsys.readouterr().out
    assert SCREEN_QUESTION in out
    assert len(agent.seen) == 1 and f"Earlier request: {REQ}" in agent.seen[0]


def test_the_command_line_with_a_pain_answer_hands_off(monkeypatch, capsys):
    agent = patch_agent(monkeypatch, [])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "my knee hurts")
    cli.main([REQ])
    assert HANDOFF_SENTENCE in capsys.readouterr().out and agent.seen == []


def test_the_command_line_with_no_terminal_prints_the_question_and_stops(monkeypatch, capsys):
    agent = patch_agent(monkeypatch, [])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    assert cli.main([REQ]) == 0
    assert SCREEN_QUESTION in capsys.readouterr().out and agent.seen == []


def test_the_flag_that_declares_no_health_issues_skips_the_question(monkeypatch, capsys):
    agent = patch_agent(monkeypatch, [ASK_MINUTES])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    cli.main([REQ, "--no-health-issues"])
    assert len(agent.seen) == 1 and SCREEN_QUESTION not in capsys.readouterr().out


def test_an_unknown_flag_still_stops_before_the_model(monkeypatch, capsys):
    agent = patch_agent(monkeypatch, [])
    assert cli.main([REQ, "--no-helth-issues"]) == 2 and agent.seen == []


# --- the chat page's server ----------------------------------------------------------------------------------

def test_the_chat_page_asks_then_plans_and_a_fresh_page_asks_again(monkeypatch, tmp_path):
    agent = patch_agent(monkeypatch, [ASK_MINUTES, ASK_MINUTES])
    app = web.App(path=tmp_path / "saved_plan.json")
    first = app.ask(REQ, fresh=True)
    assert first["text"] == SCREEN_QUESTION and first["screen"] is True and agent.seen == []
    second = app.ask("none")
    assert second["text"] == ASK_MINUTES and "Earlier request" in agent.seen[0] and not second.get("screen")
    again = app.ask(REQ, fresh=True)
    assert again["text"] == SCREEN_QUESTION  # a reloaded page is a new conversation


def test_the_chat_page_swap_of_a_recent_saved_plan_does_not_ask(monkeypatch, tmp_path):
    from homeset import saved_plan
    path = tmp_path / "saved_plan.json"
    plan = json.loads((ROOT / "evals" / "cases" / "saved_plan.json").read_text())["cases"][0]["saved_plan"]
    saved_plan.write(*_approved(plan, path), path)
    agent = patch_agent(monkeypatch, [ASK_MINUTES])
    app = web.App(path=path)
    out = app.ask("Swap the first exercise for something else.", use_saved=True, fresh=True)
    assert out["text"] != SCREEN_QUESTION and len(agent.seen) == 1


def _approved(plan, path):
    from homeset import saved_plan
    proposal = saved_plan.propose(plan, path)
    return proposal, saved_plan.confirm(proposal, "yes")


