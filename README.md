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

## Switching models (desktop app)
Only API keys need to be in `.env`. In `python app.py`, the **Models** button chooses the model for each role and saves the choice to `~/.agent_controller/models.json`. It applies from the next agent call; no restart is needed.
- Empty fields use the defaults (`OPENAI_MODEL` / `CLAUDE_MODEL` in `.env` still work as fallbacks).
- **Base URL** switches a role to another server. Planner: any OpenAI-compatible API with the Responses endpoint (Ollama `http://localhost:11434/v1`, vLLM, LM Studio). Proposer: an Anthropic-compatible API for the Claude CLI (Ollama `http://localhost:11434`).
- Local Qwen with Ollama: `ollama pull qwen3-coder`, then pick the "Local Qwen (Ollama)" preset. Give the proposer a large context window (64k+).
- Optional `LOCAL_LLM_API_KEY` in `.env` if your local server needs a key. `OPENAI_API_KEY` is still required at startup.
- The terminal (`agent_controller.main`) and browser (`agent_controller.web_ui`) versions keep using `.env`.
