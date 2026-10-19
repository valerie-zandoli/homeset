"""Chat page:  python -m homeset.web  (then open http://127.0.0.1:8000)

A local web page in front of the same agent the command line runs.  It changes how a reply
looks, not what the agent may do:  every request goes through agent.run_once(), so the
safety triggers, the tool limits, the "(assumed)" marker, and every output check still apply.

The self-playing showcase for the start of a presentation is at /showcase (it makes no
agent calls; its plans are real saved outputs).  It also opens straight from the file:
homeset/showcase.html.

Add --mock to use canned wger data (the model call still needs the API key in .env), and
--port N to change the port.

The save checkpoint is the same as on the command line (homeset/saved_plan.py):  the page
shows the saved plan next to the new one and writes only after the person clicks "Yes, save".
The click sends the answer "yes" to saved_plan.confirm(); the server keeps each proposal for
one answer and never saves on its own.

Safety of the server itself:
  - it listens on 127.0.0.1 only, so other computers cannot reach it;
  - it answers only when the Host header is this computer, and refuses a POST whose Origin
    is another site, so a web page elsewhere cannot make the browser send requests here;
  - request bodies are capped (MAX_BODY_BYTES) and messages are capped (MAX_MESSAGE_CHARS);
  - one request runs at a time (a plain HTTPServer, not a threaded one).

This module has no model code of its own and is not imported by agent.py or harness.py.
"""

from __future__ import annotations

import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import saved_plan
from .agent import run_once
from .checks import parse_plan

HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MAX_BODY_BYTES = 16384
MAX_MESSAGE_CHARS = 500
SWAP_REQUEST = "Swap the first exercise for something else."
PAGE = Path(__file__).with_name("web_page.html")
SHOWCASE = Path(__file__).with_name("showcase.html")  # self-playing opener for presentations; no agent calls
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class App:
    """The page's actions, separate from HTTP so they can be tested without a server or a model."""

    def __init__(self, search_fn=None, path: Path | None = None) -> None:
        self.search_fn = search_fn
        self.path = path or saved_plan.default_path()
        self.pending: dict[str, saved_plan.Proposal] = {}  # one answer per proposal

    def ask(self, message: object, use_saved: bool = False) -> dict:
        if not isinstance(message, str) or not message.strip():
            return {"kind": "question", "text": "What would you like?  Tell me your minutes, gear, and focus."}
        if len(message) > MAX_MESSAGE_CHARS:
            return {"kind": "question", "text": f"Please keep the request under {MAX_MESSAGE_CHARS} characters."}
        earlier = None
        if use_saved:
            earlier = saved_plan.load(self.path)
            if earlier is None:
                return {"kind": "question", "text": saved_plan.NO_SAVED_PLAN}
        try:
            if earlier:
                outcome = run_once(message.strip(), self.search_fn, earlier.plan, earlier.saved_at)
            else:
                outcome = run_once(message.strip(), self.search_fn)
        except SystemExit as err:  # agent.py exits when the key is missing; the server keeps running
            return {"kind": "error", "text": f"HomeSet cannot start:  {err}"}
        except Exception:  # a model or network failure shows a visible error, never a plan
            return {"kind": "error", "text": "Something went wrong reaching the model, so there is no plan.  Please try again."}
        reply = {"kind": outcome.kind, "text": outcome.text}
        if outcome.kind == "plan":
            reply["plan"] = plan_parts(outcome.text)
        return reply

    def propose(self, plan_text: object) -> dict:
        if not isinstance(plan_text, str):
            return {"ok": False, "text": "Not saved:  that is not a complete plan."}
        try:
            proposal = saved_plan.propose(plan_text, self.path)
        except ValueError:
            return {"ok": False, "text": "Not saved:  that is not a complete plan."}
        token = secrets.token_urlsafe(16)
        self.pending = {token: proposal}  # a newer proposal replaces an unanswered older one
        old = {"plan": proposal.old.plan, "saved_at": proposal.old.saved_at} if proposal.old else None
        return {"ok": True, "id": token, "old": old}

    def answer(self, token: object, answer: object) -> dict:
        proposal = self.pending.pop(token, None) if isinstance(token, str) else None
        if proposal is None:
            return {"saved": False, "text": "That save request has expired.  Press Save plan again."}
        approval = saved_plan.confirm(proposal, answer)  # only the exact answer "yes" approves
        if approval is None:
            return {"saved": False, "text": "Not saved.  Your earlier plan is unchanged."}
        saved_plan.write(proposal, approval, self.path)
        return {"saved": True, "text": "Saved."}


def plan_parts(text: str) -> dict | None:
    """The plan split into lines the page can lay out, or None when it cannot be read (the page then shows the text)."""
    try:
        parsed = parse_plan(text)
    except ValueError:
        return None
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    exercises = []
    for ex in parsed.exercises:
        # Without the request's known names, parse_plan splits at the first " (", so
        # "Arm Raises (T/Y/I) (bodyweight)" would show "T/Y/I) (bodyweight" as the equipment.
        # For display, split at the bracket group that closes the line instead.
        name, equipment = _split_last_group(f"{ex['name']} ({ex['equipment_text']})")
        exercises.append({**ex, "name": name, "equipment_text": equipment})
    return {
        "header": lines[0].removeprefix("HomeSet plan:").strip(),
        "exercises": exercises,
        "total": parsed.stated_total,
        "safety": lines[-1],
    }


def _split_last_group(body: str) -> tuple[str, str]:
    """'Arm Raises (T/Y/I) (bodyweight)' -> ('Arm Raises (T/Y/I)', 'bodyweight');
    'Push-Up (none (bodyweight exercise))' -> ('Push-Up', 'none (bodyweight exercise)')."""
    depth = 0
    for i in range(len(body) - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(body[i], 0)
        if depth == 0 and body[i] == "(" and i > 0 and body[i - 1] == " ":
            return body[: i - 1], body[i + 1 : -1]
    return body, ""


def _host_ok(host_header: str | None, port: int) -> bool:
    if not host_header:
        return False
    name, _, given_port = host_header.rpartition(":") if ":" in host_header else (host_header, "", "")
    return name in _LOCAL_HOSTS and given_port in ("", str(port))


def _origin_ok(origin: str | None, port: int) -> bool:
    if origin is None:  # same-origin form posts and tools like curl send no Origin
        return True
    return origin in {f"http://{h}:{port}" for h in _LOCAL_HOSTS}


def make_handler(app: App, port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep request text out of the terminal log
            sys.stderr.write(f"{self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}\n")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict) -> None:
            self._send(status, json.dumps(data).encode("utf-8"), "application/json")

        def do_GET(self):
            if not _host_ok(self.headers.get("Host"), port):
                return self._json(403, {"error": "forbidden host"})
            pages = {"/": PAGE, "/showcase": SHOWCASE}
            page = pages.get(self.path.split("?")[0])
            if page is None:
                return self._json(404, {"error": "not found"})
            self._send(200, page.read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            if not _host_ok(self.headers.get("Host"), port) or not _origin_ok(self.headers.get("Origin"), port):
                return self._json(403, {"error": "forbidden origin"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                return self._json(413, {"error": "request too large"})
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json(400, {"error": "not JSON"})
            if not isinstance(data, dict):
                return self._json(400, {"error": "not a JSON object"})
            route = self.path.split("?")[0]
            if route == "/api/ask":
                return self._json(200, app.ask(data.get("message"), bool(data.get("use_saved"))))
            if route == "/api/swap":
                return self._json(200, app.ask(SWAP_REQUEST, use_saved=True))
            if route == "/api/save/propose":
                return self._json(200, app.propose(data.get("plan")))
            if route == "/api/save/answer":
                return self._json(200, app.answer(data.get("id"), data.get("answer")))
            return self._json(404, {"error": "not found"})

    return Handler


USAGE = "usage: python -m homeset.web [--mock] [--port N]"


def main(argv: list[str]) -> int:
    port = DEFAULT_PORT
    args = list(argv)
    search_fn = None
    while args:
        flag = args.pop(0)
        if flag == "--mock":
            from .mock_wger import mock_search

            search_fn = mock_search
        elif flag == "--port" and args and args[0].isdigit():
            port = int(args.pop(0))
        else:
            print(f"Unknown option: {flag}\n{USAGE}")
            return 2
    server = HTTPServer((HOST, port), make_handler(App(search_fn), port))
    print(f"HomeSet chat is running at http://{HOST}:{port}  (Ctrl+C to stop)")
    if search_fn:
        print("[MOCK DATA: canned wger results]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
