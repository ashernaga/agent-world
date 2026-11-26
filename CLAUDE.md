# Project guide for coding agents

Multi-agent workflow with human approval. A planner model writes an investigation
plan, a proposer model (you, via the Claude CLI) inspects the repo read-only and
returns a unified diff, a human approves it, and the controller verifies and applies it.

## What you can and cannot change
- You only edit files that already exist and are tracked by Git. You cannot create,
  delete or rename files, so new features must go into an existing file.
- Protected, never propose changes to: `agent_controller/`, `scripts/`, `tests/`,
  `CLAUDE.md`, `.git*`, `.env*`, `.vscode/`.
- In practice the editable files are `app.py`, `README.md` and `requirements.txt`.
  Almost every feature belongs in `app.py`.
- Context lines in your diff must match the current file exactly (whitespace included).
  Re-read the target lines before writing a hunk, and keep hunks small.

## Layout
- `agent_controller/` (protected): the workflow itself.
  `main.py` terminal flow, `web_ui.py` local web server and page, `proposal.py` proposal
  prompt and diff validation, `approval.py` + `receipts.py` signed single-use approval,
  `patch_applier.py` verify in a temp worktree then apply, `checks.py`, `reviewer.py`,
  `openai_agent.py` (planner/reviewer client), `claude_agent.py` (runs the `claude` CLI).
- `app.py`: desktop launcher (pywebview) that subclasses the web_ui `Handler` as
  `ThemedHandler` and injects extra UI into the existing page.

## Map of app.py
- `THEME_CSS`: CSS appended to the page head. Colors come from CSS variables
  (`--bg`, `--panel`, `--btn`, ...); the light theme overrides the same variables.
- `THEME_JS`: one JavaScript block appended before `</body>`. It adds the theme
  button, Commits and Models overlays, the Copy button on chat bubbles, and the
  "Next steps" command block under GPT reviews. Placeholders `__TOKEN__` and
  `__THEME__` are replaced by `ThemedHandler._send`.
- Models: `clean_models`, `load_models`, `apply_models`, `MODELS_FILE`
  (`~/.agent_controller/models.json`, outside the repo). Applies on the next agent call.
- `ThemedHandler`: `do_GET` serves `/api/models`, `/api/branch`, `/api/commits`;
  `do_POST` serves `/api/theme` and `/api/models`; everything else goes to the parent.
- `main()`: starts the server on a free port; `--smoke` checks it and exits.

## Pitfalls (these have already caused bugs)
- `THEME_JS` is a raw string (`r"""`). Write JavaScript escapes normally (`"\n"`, `\s`).
  Do not use `\uD83E`-style surrogate pairs; use HTML entities (`&#129412;`) or plain
  characters, otherwise the server crashes with a UnicodeEncodeError.
- Never put `"""` inside `THEME_CSS` or `THEME_JS`.
- Build page text with `textContent`, not `innerHTML`: it can contain model output.
- Request bodies can be any valid JSON (`null`, `[]`). Check `isinstance(body, dict)`
  before `.get(...)`.
- Every endpoint must check `self._local_only()` and `self._authorized()` first.
- Passing user or branch names to Git: reject names starting with `-`, and never use
  force flags, `reset --hard` or `git add -p` in commands shown to the user.
- Copy-ready commands must be PowerShell-safe (single quotes, one command per line).

## Rules for changes
- Keep changes small and in the style of the surrounding code.
- Keep the README accurate: if you add or remove a UI control, update its section.
- There is no test suite. State plainly what you could not verify.
- Nothing is committed for the user. The human reviews `git diff` and commits.
