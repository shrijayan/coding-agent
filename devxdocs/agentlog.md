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

---

## [2026-07-27] Added OpenRouter as a second provider

User asked for OpenRouter support. This meant a real refactor, not just
a new file - documented here in some detail since it touches the
conversation-history design decision from the very first session.

**Why it wasn't additive-only:** `Conversation` stored messages in
Anthropic's exact wire format (a deliberate v1 shortcut - see the very
first log entry above, "revisit if a second provider is added"). OpenRouter
is OpenAI-Chat-Completions-shaped, which represents tool calls/results
structurally differently (tool calls in their own message field, tool
results as their own `role="tool"` message, vs. Anthropic folding both
into content blocks on user/assistant messages). Reusing Anthropic's
format wouldn't have worked, so this was the right time to introduce a
neutral format, per YAGNI - not before it was needed, but also not
avoided once it was.

**Research done before writing any code** (to avoid guessing wrong API
shapes):
- Fetched OpenRouter's docs. Found their `@openrouter/agent` package
  (automatic tool-use loop, like our AgentLoop) is **TypeScript only**
  - Python only gets the low-level Client SDK where "you manage tool
    dispatch yourself." Good outcome: confirms we keep our own AgentLoop
    as the orchestrator regardless, we're not tempted to outsource it.
  - Confirmed OpenRouter's docs explicitly recommend the official
    `openai` Python SDK pointed at `base_url="https://openrouter.ai/api/v1"`
    as a supported drop-in-replacement pattern - used that instead of
    hand-rolling HTTP or using OpenRouter's newer, less-established
    native Python package.
  - Queried OpenRouter's live `/api/v1/models` endpoint to confirm
    `anthropic/claude-sonnet-5` and `openai/gpt-5.1` are real, current
    model slugs before putting them in docs/config examples.
  - Confirmed `max_tokens` (not the newer `max_completion_tokens`) is
    the universally-supported param across OpenRouter's proxied models.
- Inspected the installed `openai` SDK's actual types (`ChatCompletionMessage`,
  tool call/result message shapes, exception hierarchy) the same way we
  inspected `anthropic`'s types in an earlier session - never assumed
  the two SDKs matched just because they look similar.

**What changed:**
- New `llm/messages.py`: neutral `Message`/`TextPart`/`ToolUsePart`/
  `ToolResultPart` types. This is now the one conversation format the
  rest of the app understands.
- `llm/base.py`: `LLMResponse` simplified - dropped `raw_content` (no
  longer needed, an assistant turn can be reconstructed from `text` +
  `tool_calls`) and dropped the raw `stop_reason` string (Anthropic and
  OpenAI-style APIs signal "wants more tools" completely differently -
  `stop_reason == "tool_use"` vs. a non-empty `tool_calls` list - so each
  client now resolves that difference itself into one plain
  `wants_tool_use: bool`, instead of leaking either provider's enum
  values through the shared interface).
- `agent/conversation.py`: stores `list[Message]` (neutral) instead of
  Anthropic-shaped dicts.
- `llm/anthropic_client.py`: now translates neutral <-> Anthropic's
  wire format (`_to_anthropic_messages`); response parsing otherwise
  unchanged.
- `llm/openrouter_client.py` (new): translates neutral <-> OpenAI Chat
  Completions format via `_to_openai_messages`/`_to_openai_tool`; uses
  the `openai` SDK pointed at OpenRouter.
- `config.py`: added `AGENT_PROVIDER` (`anthropic` | `openrouter`,
  fail-fast if neither). Only the API key env var matching the selected
  provider is required - e.g. `OPENROUTER_API_KEY` is never checked when
  `AGENT_PROVIDER=anthropic`. Mapping of provider -> its key's env var
  name lives in `_PROVIDER_API_KEY_ENV_VARS`, treated as fixed program
  wiring, not environment config.
- `llm/factory.py` (new): `build_llm_client(config)` - the one place
  that knows every provider's concrete class.
- `cli.py`: uses the factory instead of hardcoding `AnthropicClient`;
  startup line now prints `(provider / model)` so it's obvious which
  backend is active.
- `.env.example`, `README.md`, `AGENTS.md`: all updated for the two-
  provider setup (README gets a proper "Option A / Option B" table in
  the setup steps; AGENTS.md's "Adding a second LLM provider (if/when
  needed)" section became "Adding a new LLM provider" with a concrete,
  accurate recipe now that it's been done once for real).

**A real bug caught by testing rather than assuming:** initially wrote
`OpenRouterClient._describe()` copying AnthropicClient's error-body
extraction (`body["error"]["message"]`). Triggered a real 401 against
OpenRouter to verify the clean-message output, and the extraction
silently failed - the `openai` SDK's `.body` is *already* the unwrapped
inner error object (`{"message": ..., "code": 401}`), unlike `anthropic`'s
`.body` which keeps the outer `"error"` key. Fixed by inspecting the
actual object returned, not by assuming the two generated SDKs behave
identically because they look alike on the surface.

**Verified manually:**
1. Full regression on the Anthropic path after the refactor: a single
   request that chained list_files -> bash -> write_file -> read_file ->
   edit_file -> read_file (5 tool calls in one turn) still worked
   end-to-end.
2. Config validation: missing `AGENT_PROVIDER`, invalid provider value,
   and "openrouter selected but OPENROUTER_API_KEY missing" all produce
   the expected fail-fast errors (tested in an isolated `env -i` shell to
   rule out `.env`/shell env leaking into the test).
3. OpenRouter plumbing end-to-end *except* a successful model response
   (no real OpenRouter key available yet): deliberately invalid key ->
   real HTTP call reached OpenRouter's servers -> clean
   `error> OpenRouter returned an error (401): Missing Authentication header`
   -> session stayed alive. Confirms config, factory, and error-handling
   all work; only the "happy path with a real key" is unverified.
4. Unit-verified both translation functions directly (no network) with a
   simulated multi-turn tool-use conversation, and checked the JSON output
   matches each provider's documented shape exactly.

**Not yet done:** a live successful OpenRouter tool-calling round trip -
user didn't have an OpenRouter key on hand this session. Whoever picks
this up next: get a key at openrouter.ai/keys, set
`AGENT_PROVIDER=openrouter` + `OPENROUTER_API_KEY` +
`AGENT_MODEL=anthropic/claude-sonnet-5` (or any model slug) in `.env`,
and run through the same demo prompts from the README to confirm.
