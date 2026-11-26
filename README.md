# agents world

Multi-agent workflow with human approval: GPT plans, Claude proposes a diff, you approve, the patch is verified in a temporary worktree and applied, then checked and reviewed.

## Setup
1. `pip install -r requirements.txt` (Python 3.10+).
2. Install the Claude CLI (`claude` must work in a terminal).
3. Create a `.env` file in the project root containing at least `OPENAI_API_KEY=...`. Optional: `OPENAI_MODEL`, `CLAUDE_MODEL`, `LOCAL_LLM_API_KEY`.
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
The window runs in the background, so the terminal is free again as soon as it opens; its output goes to `~/.agent_controller/app.log`. `python app.py --console` keeps it in the terminal instead.
The browser and terminal versions keep working.
`python app.py --smoke` starts the server, checks that it responds, and exits without opening a window.

### Using it on another project
The agents work on the Git repository in the current folder, or on the one given with `--project`. Nothing from this folder has to be copied into that project. Example (PowerShell): `python 'C:\path\to\agents-world\app.py' --project 'C:\path\to\new-project'`
- The project must be a Git repository with at least one commit and no uncommitted changes.
- API keys stay in this folder's `.env`. A `.env` in the target project can still set `CLAUDE_MODEL`.
- Task history is kept per project in `~/.agent_controller/<project folder name>.json`.
- The same protected paths apply there (`agent_controller/`, `scripts/`, `tests/`, `CLAUDE.md`, `.git*`, `.env*`).

Extra controls in the desktop app:
- **Git**: read-only overview of the repository (remote, current branch, changed files, local and remote branches).
- **Commits**: the last 50 commits.
- **Models**: per-role model choice (see below).
- **Tokens**: token usage of every agent call (input, output, total), grouped by task, with a session total; the button shows the running total. Claude counts include cached input and the cost reported by the CLI. Counts are kept in memory until the app closes; "-" means the server did not report usage.
- Theme button: switches between light and dark mode; the choice is saved to `~/.agent_controller/theme.txt`.
- **Next steps**: after the GPT review of an applied change, copyable Git commands to commit it, commit it to a new `agent/...` branch (offered first when you are on `main` or `master`), or undo it while it is still uncommitted.

## Switching models (desktop app)
Only API keys need to be in `.env`. In `python app.py`, the **Models** button chooses the model for each role and saves the choice to `~/.agent_controller/models.json`. It applies from the next agent call; no restart is needed.
- Empty fields use the defaults (`OPENAI_MODEL` / `CLAUDE_MODEL` in `.env` still work as fallbacks).
- **Base URL** switches a role to another server. Planner: any OpenAI-compatible API with the Responses endpoint (Ollama `http://localhost:11434/v1`, vLLM, LM Studio). Proposer: an Anthropic-compatible API for the Claude CLI (Ollama `http://localhost:11434`).
- Local Qwen with Ollama: `ollama pull qwen3-coder`, then pick the "Local Qwen (Ollama)" preset. Give the proposer a large context window (64k+).
- Optional `LOCAL_LLM_API_KEY` in `.env` if your local server needs a key. `OPENAI_API_KEY` is still required at startup.
- The terminal (`agent_controller.main`) and browser (`agent_controller.web_ui`) versions keep using `.env`.

## Agent compatibility

The workflow is organized by role, not tied to one vendor. Each role can use any model served through a compatible API:
- **Planner and reviewer (GPT role):** any OpenAI-compatible server with the Responses endpoint (OpenAI, Ollama, vLLM, LM Studio).
- **Proposer (Claude role):** the Claude CLI, talking to Anthropic or any Anthropic-compatible endpoint (for example Ollama).
- Other agents (different CLIs or custom tools) are not plugged in yet. Supporting one means adding an adapter alongside `agent_controller/openai_agent.py` and `agent_controller/claude_agent.py`.

## Multi-agent workflow environment

Running the app sets up a controlled environment in which the agents cooperate on one task:
1. The planner turns your request into an investigation plan.
2. The proposer inspects the repository read-only and returns a unified diff.
3. You approve or reject the diff.
4. The patch is verified in a temporary Git worktree, then applied to your working tree.
5. Checks run and the reviewer reports on the applied change.

Model choices per role are set in the desktop app's **Models** panel (see above); task history is kept in `~/.agent_controller/`.

## Safety and limits
- Nothing is staged or committed for you. Inspect an applied change with `git diff`; the result also shows an undo command.
- Approval creates a signed, single-use receipt tied to the exact diff and the current commit. A stale or edited proposal is refused.
- Proposals can only edit existing files tracked by Git. They cannot touch `agent_controller/`, `scripts/`, `tests/`, `CLAUDE.md`, `.git*` files or `.env*` files; change those by hand.
- Checks: a Python syntax check of the changed files, plus `python -m unittest discover -s tests` if a `tests/` folder exists (15-minute timeout).
- Check results are only reported; they do not roll back the change.
