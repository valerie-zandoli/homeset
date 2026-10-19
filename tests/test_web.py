"""The chat page's server (homeset/web.py).  No model, no network beyond this computer.

run_once is replaced with a stand-in, so these tests check the page's plumbing and the save
checkpoint, not the agent.  The agent itself is covered by the other test files.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from homeset import saved_plan, web
from homeset.checks import HANDOFF_SENTENCE
from homeset.harness import Outcome

CASES = json.loads((Path(saved_plan.ROOT) / "evals" / "cases" / "saved_plan.json").read_text())["cases"]
PLAN_A = CASES[0]["saved_plan"]  # a real plan from a live run
PLAN_B = CASES[1]["saved_plan"]


@pytest.fixture
def path(tmp_path):
    return tmp_path / "saved_plan.json"


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_run_once(message, search_fn=None, earlier_plan=None, earlier_plan_at=""):
        seen.append({"message": message, "earlier_plan": earlier_plan})
        if "hurt" in message:
            return Outcome(kind="handoff", text=HANDOFF_SENTENCE)
        return Outcome(kind="plan", text=PLAN_B if earlier_plan else PLAN_A)

    monkeypatch.setattr(web, "run_once", fake_run_once)
    return seen


# --- the page's actions ---------------------------------------------------------------------------


def test_a_request_goes_through_run_once_and_comes_back_as_a_plan(path, calls):
    reply = web.App(path=path).ask("I have 15 minutes and a mat.  Legs.")
    assert calls[0]["message"] == "I have 15 minutes and a mat.  Legs."
    assert reply["kind"] == "plan" and reply["text"] == PLAN_A
    assert reply["plan"]["exercises"] and reply["plan"]["safety"].startswith("Stop if anything hurts")


def test_a_hand_off_is_passed_through_word_for_word_with_no_plan(path, calls):
    reply = web.App(path=path).ask("My knee hurts.  15 minutes, legs.")
    assert reply == {"kind": "handoff", "text": HANDOFF_SENTENCE}


@pytest.mark.parametrize("message", ["", "   ", None, 42, "x" * (web.MAX_MESSAGE_CHARS + 1)])
def test_an_empty_or_oversized_message_never_reaches_the_model(path, calls, message):
    assert web.App(path=path).ask(message)["kind"] == "question"
    assert calls == []


def test_a_swap_with_nothing_saved_asks_for_a_plan_first(path, calls):
    reply = web.App(path=path).ask(web.SWAP_REQUEST, use_saved=True)
    assert reply["text"] == saved_plan.NO_SAVED_PLAN and calls == []


def test_a_swap_starts_from_the_saved_plan(path, calls):
    app = web.App(path=path)
    token = app.propose(PLAN_A)["id"]
    assert app.answer(token, "yes")["saved"]
    app.ask(web.SWAP_REQUEST, use_saved=True)
    assert calls[-1]["earlier_plan"] == PLAN_A.strip()


# --- the save checkpoint --------------------------------------------------------------------------


def test_saving_needs_the_yes_click(path):
    app = web.App(path=path)
    proposal = app.propose(PLAN_A)
    assert proposal["ok"] and proposal["old"] is None and not path.exists()
    assert app.answer(proposal["id"], "yes") == {"saved": True, "text": "Saved."}
    assert saved_plan.load(path).plan == PLAN_A.strip()


@pytest.mark.parametrize("answer", ["no", "", None, "y", "yes please", 1, True])
def test_anything_but_yes_saves_nothing(path, answer):
    app = web.App(path=path)
    token = app.propose(PLAN_A)["id"]
    assert app.answer(token, answer)["saved"] is False and not path.exists()


def test_the_page_shows_the_plan_a_save_would_replace(path):
    app = web.App(path=path)
    app.answer(app.propose(PLAN_A)["id"], "yes")
    old = app.propose(PLAN_B)["old"]
    assert old["plan"] == PLAN_A.strip() and old["saved_at"]


def test_each_save_request_takes_one_answer_only(path):
    app = web.App(path=path)
    token = app.propose(PLAN_A)["id"]
    app.answer(token, "no")
    assert app.answer(token, "yes")["saved"] is False and not path.exists()


def test_an_unknown_or_replaced_save_request_saves_nothing(path):
    app = web.App(path=path)
    old_token = app.propose(PLAN_A)["id"]
    app.propose(PLAN_B)  # a newer proposal replaces the unanswered one
    assert app.answer(old_token, "yes")["saved"] is False
    assert app.answer("made-up", "yes")["saved"] is False and not path.exists()


@pytest.mark.parametrize("text", [HANDOFF_SENTENCE, "not a plan", None, 5])
def test_only_a_complete_plan_can_be_offered_for_saving(path, text):
    assert web.App(path=path).propose(text)["ok"] is False


# --- the HTTP server ------------------------------------------------------------------------------


@pytest.fixture
def server(path, calls):
    httpd = HTTPServer(("127.0.0.1", 0), web.make_handler(web.App(path=path), 0))
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = web.make_handler(web.App(path=path), port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield port
    httpd.shutdown()
    httpd.server_close()


def request(port, route, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{route}", data=data, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_the_page_loads(server):
    status, body = request(server, "/")
    assert status == 200 and b"HomeSet" in body


def test_ask_over_http(server):
    status, body = request(server, "/api/ask", {"message": "I have 15 minutes and a mat.  Legs."})
    assert status == 200 and json.loads(body)["kind"] == "plan"


def test_a_request_from_another_website_is_refused(server, calls):
    status, _ = request(server, "/api/ask", {"message": "15 minutes"}, {"Origin": "https://evil.example"})
    assert status == 403 and calls == []


def test_a_request_for_another_host_name_is_refused(server, calls):
    status, _ = request(server, "/api/ask", {"message": "15 minutes"}, {"Host": "evil.example"})
    assert status == 403 and calls == []


def test_an_oversized_body_is_refused(server, calls):
    status, _ = request(server, "/api/ask", {"message": "x" * (web.MAX_BODY_BYTES + 10)})
    assert status == 413 and calls == []


def test_unknown_routes_are_not_found(server):
    assert request(server, "/secret")[0] == 404
    assert request(server, "/api/nope", {})[0] == 404


def test_the_server_listens_on_this_computer_only():
    assert web.HOST == "127.0.0.1"


def test_the_model_side_modules_never_import_the_web_server():
    for module in ("agent.py", "harness.py"):
        assert "web" not in (Path(saved_plan.ROOT) / "homeset" / module).read_text().replace("wger", "")


def test_a_missing_key_shows_an_error_and_the_server_keeps_running(path, monkeypatch):
    def no_key(*a, **k):
        raise SystemExit("ANTHROPIC_API_KEY is missing or still a placeholder in .env")

    monkeypatch.setattr(web, "run_once", no_key)
    reply = web.App(path=path).ask("I have 15 minutes and a mat.")
    assert reply["kind"] == "error" and "ANTHROPIC_API_KEY" in reply["text"] and "plan" not in reply


def test_a_model_failure_shows_an_error_not_a_plan(path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("timeout")

    monkeypatch.setattr(web, "run_once", boom)
    reply = web.App(path=path).ask("I have 15 minutes and a mat.")
    assert reply["kind"] == "error" and "plan" not in reply


@pytest.mark.parametrize(
    "body, name, equipment",
    [
        ("Arm Raises (T/Y/I) (bodyweight)", "Arm Raises (T/Y/I)", "bodyweight"),
        ("Push-Up (none (bodyweight exercise))", "Push-Up", "none (bodyweight exercise)"),
        ("Pike Hold (Floor) (mat)", "Pike Hold (Floor)", "mat"),
        ("Crunches (mat)", "Crunches", "mat"),
    ],
)
def test_names_with_brackets_display_whole(body, name, equipment):
    assert web._split_last_group(body) == (name, equipment)
