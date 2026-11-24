# agents world

Multi-agent workflow with human approval: GPT plans, Claude proposes a diff, you approve, the patch is verified in a temporary worktree and applied, then checked and reviewed.

## Setup
1. `pip install -r requirements.txt`
2. Install the Claude CLI (`claude` must work in a terminal).
3. Copy `.env.example` to `.env` and add `OPENAI_API_KEY`.
4. Commit your files (the controller refuses to run with uncommitted changes).
5. Run `python -m agent_controller.main` from this folder.

## Web window (instead of the terminal)
`python -m agent_controller.web_ui` opens a local page at http://127.0.0.1:8765 with:
chat with all agents, step progress, a colored diff with Approve/Reject buttons, and task history.
The terminal version (`python -m agent_controller.main`) still works.
History is stored outside the repo in `~/.agent_controller/`.

## Desktop app (native window)
`python app.py` opens the same interface in its own desktop window instead of a browser tab.
It needs `pywebview` (included in `requirements.txt`) and runs the local server on a free port.
The browser and terminal versions keep working.
