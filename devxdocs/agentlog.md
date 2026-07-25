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
