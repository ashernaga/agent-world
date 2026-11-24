"""
Local web window for the multi-agent approval workflow.

Run from the project root:   python -m agent_controller.web_ui

It serves a page on 127.0.0.1 only. The workflow is the same as
main.py (plan -> proposal -> human approval -> verified apply ->
checks -> review); only the terminal is replaced by a browser page.
Standard library only, no extra packages.
"""

import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .openai_agent import ask_gpt
from .proposal import generate_proposal
from .approval import prepare_approval, finalize_approval
from .patch_applier import apply_approved_patch, ensure_clean_working_tree
from .checks import run_checks, format_checks
from .reviewer import get_working_diff, review_change

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAGE = (Path(__file__).resolve().parent / "web" / "index.html")

# History is kept outside the repository so it never dirties the working
# tree (the controller refuses to run when the tree has changes).
HISTORY_FILE = Path.home() / ".agent_controller" / f"{PROJECT_ROOT.name}.json"

HOST = "127.0.0.1"
PORT = 8765
TOKEN = secrets.token_urlsafe(24)  # new on every start; the page embeds it
APPROVAL_TIMEOUT_SECONDS = 3600

STEPS = [
    "GPT plans",
    "Claude proposes",
    "You approve",
    "Verify & apply",
    "Checks",
    "GPT reviews",
]


class Session:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = []
        self.status = "idle"  # idle | running | awaiting_approval
        self.step = 0
        self.pending = None
        self.decision = None
        self.decision_event = threading.Event()
        self.current = None

    def emit(self, kind, agent, text, **data):
        with self.lock:
            event = {
                "id": len(self.events),
                "ts": time.strftime("%H:%M:%S"),
                "kind": kind,
                "agent": agent,
                "text": text,
                "data": data,
            }
            self.events.append(event)

    def set_step(self, number):
        with self.lock:
            self.step = number

    def snapshot(self, since):
        with self.lock:
            pending = None
            if self.pending:
                p = self.pending["proposal"]
                pending = {
                    "summary": p["summary"],
                    "details": p["details"],
                    "files": p["files"],
                    "diff": p["diff"],
                }
            return {
                "status": self.status,
                "step": self.step,
                "steps": STEPS,
                "pending": pending,
                "events": self.events[since:],
                "next": len(self.events),
            }


S = Session()


def load_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_history(record):
    history = load_history()
    history.insert(0, record)
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(history[:200], indent=2), encoding="utf-8"
    )


def planning_prompt(task):
    return f"""
You are the planning agent for this Python project.

User task:
{task}

Create a concise investigation plan for Claude Code.
Tell Claude which files and functions to inspect.

Do not pretend you have inspected the local files.
Do not modify any files.
"""


def run_task(task):
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "task": task,
        "outcome": "failed",
        "summary": "",
        "files": [],
        "undo": "",
    }

    try:
        try:
            ensure_clean_working_tree()
        except ValueError as error:
            S.emit(
                "error", "Controller",
                "Cannot start: the project has uncommitted changes. "
                "Commit or undo them, then try again.\n\n" + str(error),
            )
            record["outcome"] = "not started"
            return

        S.set_step(1)
        S.emit("step", "Controller", "GPT is preparing an investigation plan...")
        plan = ask_gpt(planning_prompt(task))
        S.emit("agent", "GPT", plan)

        S.set_step(2)
        S.emit("step", "Controller", "Claude is inspecting the project and writing a proposal (can take a few minutes)...")
        proposal = generate_proposal(task=task, investigation_plan=plan)
        record["summary"] = proposal["summary"]
        record["files"] = proposal["files"]
        S.emit("agent", "Claude", proposal["summary"] + "\n\n" + proposal["details"])

        S.set_step(3)
        try:
            baseline, diff_hash = prepare_approval(proposal)
        except (ValueError, RuntimeError) as error:
            S.emit("error", "Controller", f"Proposal rejected by validation: {error}\nNo changes were made.")
            record["outcome"] = "invalid proposal"
            return

        with S.lock:
            S.pending = {"proposal": proposal}
            S.decision = None
            S.decision_event.clear()
            S.status = "awaiting_approval"
        S.emit("approval", "Controller", "Waiting for your decision. Review the diff on the right.")

        answered = S.decision_event.wait(APPROVAL_TIMEOUT_SECONDS)
        with S.lock:
            decision = S.decision if answered else "reject"
            S.pending = None
            S.status = "running"

        if decision != "approve":
            S.emit("system", "Controller", "Proposal rejected. No files were modified.")
            record["outcome"] = "rejected"
            return

        try:
            receipt = finalize_approval(baseline, diff_hash)
        except (ValueError, RuntimeError) as error:
            S.emit("error", "Controller", f"Approval verification failed: {error}\nA new proposal is required.")
            record["outcome"] = "approval failed"
            return

        S.set_step(4)
        S.emit("step", "Controller", "Verifying in a temporary worktree, then applying the approved diff...")
        result = apply_approved_patch(proposal, receipt)
        record["undo"] = result["undo_command"]
        S.emit(
            "result", "Controller",
            "Patch applied (not staged, not committed).\nFiles changed:\n"
            + "\n".join("  - " + f for f in result["changed_files"])
            + "\n\nTo undo:\n  " + result["undo_command"],
        )

        S.set_step(5)
        S.emit("step", "Controller", "Running checks...")
        checks = run_checks(result["changed_files"])
        checks_text = format_checks(checks)
        S.emit("checks", "Controller", checks_text)

        S.set_step(6)
        S.emit("step", "Controller", "GPT is reviewing the applied change...")
        try:
            diff = get_working_diff(result["changed_files"])
            S.emit("agent", "GPT", review_change(task, proposal, diff, checks_text))
        except Exception as error:
            S.emit("error", "Controller", f"Review could not be completed: {error}\nThe change was still applied; review it yourself.")

        record["outcome"] = "applied"
        S.emit("system", "Controller", "Done. The change is in your working tree and is NOT committed. Inspect with `git diff`.")

    except Exception as error:
        S.emit("error", "Controller", f"Error: {error}")
    finally:
        save_history(record)
        with S.lock:
            S.status = "idle"
            S.step = 0
            S.pending = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj))

    def _local_only(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _authorized(self):
        return secrets.compare_digest(
            self.headers.get("X-Token", ""), TOKEN
        )

    def do_GET(self):
        if not self._local_only():
            return self._send(403, "forbidden", "text/plain")

        path, _, query = self.path.partition("?")

        if path == "/":
            html = PAGE.read_text(encoding="utf-8")
            html = html.replace("__TOKEN__", TOKEN).replace(
                "__PROJECT__", PROJECT_ROOT.name
            )
            return self._send(200, html, "text/html")

        if not self._authorized():
            return self._json({"error": "unauthorized"}, 401)

        if path == "/api/state":
            since = 0
            for part in query.split("&"):
                if part.startswith("since="):
                    since = int(part[6:] or 0)
            return self._json(S.snapshot(since))

        if path == "/api/history":
            return self._json(load_history())

        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._local_only() or not self._authorized():
            return self._json({"error": "unauthorized"}, 401)

        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, 400)

        if self.path == "/api/task":
            task = str(body.get("task", "")).strip()
            if not task:
                return self._json({"error": "empty task"}, 400)
            with S.lock:
                if S.status != "idle":
                    return self._json({"error": "a task is already running"}, 409)
                S.status = "running"
            S.emit("user", "You", task)
            threading.Thread(target=run_task, args=(task,), daemon=True).start()
            return self._json({"ok": True})

        if self.path in ("/api/approve", "/api/reject"):
            with S.lock:
                if S.status != "awaiting_approval":
                    return self._json({"error": "nothing to approve"}, 409)
                S.decision = "approve" if self.path.endswith("approve") else "reject"
            S.decision_event.set()
            return self._json({"ok": True})

        self._json({"error": "not found"}, 404)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Agent window running at {url}  (Ctrl+C to stop)")
    print(f"Project: {PROJECT_ROOT}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
