# Agent Log

Append-only log of work done on this repo. If you're picking up this
project, read the most recent entries below - no need to read the whole
history unless you want it.

---

## [2026-07-25] Initial build - v1 bare-minimum agent loop

Built the first working version from an empty repo. Stack: Python 3.12 +
`uv`, Anthropic SDK, model `claude-sonnet-5`. No other frameworks.

What exists:
- `config.py` - fails fast if any required env var (ANTHROPIC_API_KEY,
  AGENT_MODEL, AGENT_MAX_TOKENS, AGENT_MAX_ITERATIONS,
  AGENT_BASH_TIMEOUT_SECONDS) is missing or invalid. No hidden defaults.
- `llm/base.py` (LLMClient interface) + `llm/anthropic_client.py`
  (concrete implementation calling the Anthropic Messages API).
- `tools/base.py` (Tool interface + ToolResult) + 5 tools: read_file,
  write_file, edit_file (exact-match find/replace, fails if old_text
  isn't unique), bash (subprocess, configurable timeout), list_files
  (recursive, skips .git/__pycache__/.venv/node_modules).
- `tools/registry.py` - ToolRegistry dispatches calls by name; tools are
  passed into its constructor, not created internally.
- `agent/loop.py` - AgentLoop: send conversation to Claude -> if it asks
  for tools, run them and feed results back -> repeat until it returns
  plain text. Capped at AGENT_MAX_ITERATIONS (raises
  AgentLoopSafetyLimitError if a run never converges).
- `agent/conversation.py` - message history stored directly in
  Anthropic's wire format (no extra translation layer - not needed with
  a single provider; would revisit if a second provider is added).
- `cli.py` - REPL: builds the agent from Config, reads from stdin,
  prints `[tool] name(args)` before each tool call, then the final
  answer.

Verified manually (no automated tests yet - v1 scope was "bare minimum"):
1. Fail-fast config: running with AGENT_MODEL unset exits immediately
   with a clear error message and exit code 1.
2. End-to-end happy path: asked the agent to create a Python file with
   an `add()` function and run it - it called write_file then bash and
   reported the correct output.
3. list_files + read_file + edit_file: asked it to list a directory,
   read a file, change one line via exact-match replace, and rerun it -
   all tools worked and the file content on disk changed correctly.
4. Error recovery: asked it to read a file that doesn't exist -
   ReadFileTool returned ToolResult.error(...), the harness did not
   crash, and the model reported the error in plain English back to the
   user. Confirms "fail fast on config, recover gracefully on tool
   errors" actually holds at runtime, not just in theory.

Decisions worth knowing if you continue this:
- Anthropic-only by design for v1. LLMClient is already an interface so
  adding a second provider later is additive - but don't build it before
  it's actually needed (YAGNI).
- No permission prompts before bash/write yet (explicit v1 scope
  decision). If this ever runs somewhere less trusted than a personal
  machine, add a confirm-before-run step to BashTool/WriteFileTool first
  - that's the natural next safety feature, not an afterthought.
- Model name, token limits, timeouts, and iteration cap are all env-
  driven (see .env.example), never hardcoded - see AGENTS.md conventions.

Natural next steps (not started): permission prompts, session
save/resume, streaming output, grep/glob search tools, automated tests.

---

## [2026-07-25] Pushed to GitHub (private) + wrote a real README

- Ran `git init` (already done earlier this session) then
  `gh repo create coding-agent --private --source=. --remote=origin --push`.
  Repo is at https://github.com/shrijayan/coding-agent, confirmed
  `visibility: PRIVATE` via `gh repo view`. `.env` stayed untracked
  (gitignored) - only `.env.example` went up.
- Rewrote README.md from an empty placeholder into a full setup/usage
  guide, explicitly aimed at non-engineers (business users, beginners,
  students) since this project is being used for demos. Structure: what
  it is (with a plain analogy) -> a real example transcript -> what it
  can/can't do -> prerequisites -> numbered setup steps (install uv, get
  the code, `uv sync`, get an API key, configure `.env`, run it) -> demo
  prompts to try -> settings reference table -> troubleshooting table ->
  safety note -> pointer to AGENTS.md for the internals.
- Every command and error message quoted in the README was actually run,
  not guessed - including the demo transcript in section 1, the
  multi-step notes.txt demo, and the Fibonacci demo, all in a scratch
  temp folder outside the repo.
- Finding while verifying the troubleshooting table: an API-level failure
  (tested with a deliberately invalid key) is NOT caught anywhere today -
  it crashes the whole CLI with a raw Python traceback instead of a clean
  message, unlike tool errors (file not found, etc.) which already
  recover gracefully. Documented this honestly in the README as a known
  limitation rather than glossing over it. Not fixed yet - flagged to the
  user as the natural next improvement (wrap the `AnthropicClient.send()`
  call in `cli.py`/`AgentLoop` with a narrow except for the Anthropic SDK's
  API error types, print a clean message, keep the REPL alive).

---

## [2026-07-25] Fixed: API errors no longer crash the CLI

User asked to fix the gap logged above. Extended the existing "recover
gracefully" convention (previously only for tool errors) to cover
LLM/API errors too:

- Added `LLMError` to `llm/base.py` - a provider-agnostic exception.
  `LLMClient.send()`'s docstring now documents that it can raise this.
- `anthropic_client.py` now catches `anthropic.APIError` (the SDK's base
  class covering auth errors, rate limits, connection issues, timeouts,
  bad requests, and server errors - verified the exact class hierarchy
  by inspecting the installed SDK rather than guessing) around the
  `messages.create()` call, and re-raises as `LLMError` with a short,
  clean, human-readable message. Wrote a `_describe()` helper that pulls
  the actual reason out of the error's `.body` dict (e.g.
  `"invalid x-api-key"`) instead of surfacing the SDK's full raw message
  (which includes request IDs and nested dicts - noise for an end user).
- `cli.py` now catches `LLMError` around `agent.run_turn(...)`, prints
  one `error> ...` line, and `continue`s the input loop instead of
  letting the exception kill the whole program.
- `AgentLoop` itself needed no change - `LLMError` just propagates up
  through it naturally, same as before, and `cli.py` (the I/O boundary)
  is where it gets caught, consistent with how `MissingConfigError` is
  already handled there.

Before writing the rollback logic I assumed I'd need (removing the
user's message from history on failure so a retry doesn't leave two
consecutive `role: user` messages), I actually tested it against the
real API first: consecutive user-role messages are accepted fine, so no
rollback needed - kept the fix minimal instead of over-engineering it.

Verified manually:
1. Bad key -> clean `error> Claude API returned an error (401): invalid
   x-api-key` line, session stays open, tried again immediately without
   restarting.
2. Valid key, no tools -> still answers normally.
3. Valid key, with tools (write_file + read_file) -> still works
   end-to-end, confirming the response-parsing path wasn't broken by
   adding the try/except around it.

Updated README.md's troubleshooting table and "reading the screen"
section to describe the new `error>` line instead of the old
"crashes the session" behavior. Updated AGENTS.md's conventions section
and module map to mention `LLMError` alongside the other exception types.
