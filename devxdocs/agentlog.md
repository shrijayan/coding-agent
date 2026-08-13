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

---

## [2026-07-27] Workshop context established + token/cost tracking +
## optimization extension-point scaffolding

This session's real news: this repo is the shared **Base Agent for a
workshop on agent cost/performance optimization** (user, "Krishna", and
"KP" each building one optimization on top of it - conversation
summary + MCP/tool-calling comparison for the user, caching + model
routing for Krishna, observability + context-window-optimization +
agent-loop-prevention for KP, a couple of pieces still unassigned). The
workshop narrative: run the same prompt, flip an optimization on,
rerun, and show token/cost savings *alongside* a performance/correctness
check - not cost savings in isolation, since a cheaper-but-worse agent
isn't actually an improvement. Captured in AGENTS.md's "What this is"
now so this context survives across sessions/contributors, not just in
chat history.

Extensive back-and-forth on **why SWE-bench matters and how a
benchmark should relate to interactive usage** - worth preserving the
conclusion since it shapes the still-unbuilt benchmark runner:
- SWE-bench (or a subset) is the *performance ruler* - it has real
  hidden tests, so "resolved 4/5 before, 4/5 after, 40% fewer tokens" is
  checkable, unlike an arbitrary user prompt which has no ground truth.
- Official SWE-bench harness needs Docker, ~120GB disk, 16GB+ RAM, and
  ~60 environment images - fine for a one-time offline validation, wrong
  for a live workshop loop. Decision: build our own lightweight,
  Docker-free runner using real SWE-bench Lite instances (real issues,
  real FAIL_TO_PASS/PASS_TO_PASS tests) - 3-5 hand-picked, pre-verified,
  low-dependency instances, not a general "any instance" loader. NOT
  YET BUILT this session - was going to be next, then the user redirected
  to token/cost tracking + AGENTS.md documentation first (see below).
- Benchmark tasks and interactive `/usage` sessions are **deliberately
  decoupled**, not one blended command: the benchmark must run a FIXED
  prompt every time (otherwise a cost difference could just mean the
  task changed, not that the optimization helped) - so it can never
  depend on whatever a user happens to type interactively. `/usage`
  (this session's real tokens/cost) and a future benchmark report
  (fixed tasks, pass-rate + tokens/cost together) are two separate
  tools for two separate jobs, not one.

**Built this session (in commit order - see individual commit messages
for full detail):**

1. `metrics/usage.py` + `metrics/pricing.py` + `metrics/pricing.json` -
   real token counts (never estimated) from every model call, turned
   into a cost estimate via a hand-maintained pricing file. Fails fast
   at startup if the configured model has no price entry (user's
   explicit call: hardcode prices in a plain file rather than build a
   live OpenRouter pricing lookup - not worth the complexity for a
   workshop with a small, known set of models).
2. `commands/` (SlashCommand + SlashCommandRegistry, mirrors
   Tool/ToolRegistry) + `/usage` - prints tokens, cost, and call counts
   for the session. Verified cost math by hand against real numbers
   twice ($0.0029 and $0.0095) - both matched exactly.
3. **Optimization extension-point scaffolding** (`optimizations/`
   package + `cli_args.py`), built specifically because the user wanted
   AGENTS.md to guide colleagues' own coding agents toward building
   their optimization *without* it being explained to them verbally -
   which meant the extension point had to actually exist first, not
   just be planned:
   - `OptimizationBundle` (3 optional fields: `history_policy`,
     `wrap_llm_client`, `system_prompt_suffix`) covers the 3 kinds of
     changes an optimization can make, matching the 9 workshop
     optimization areas from the spreadsheet.
   - `HistoryPolicy` interface + `DefaultHistoryPolicy` (send everything
     - today's behavior, now expressed as the default of a swappable
     interface). `AgentLoop` now routes history through
     `policy.prepare()` before every model call.
   - `OptimizationRegistry` (mirrors ToolRegistry) resolves `--enable`
     names into a combined bundle; fails fast on unknown names.
   - Bundle composition when multiple `--enable` values are given:
     `wrap_llm_client` wrappers chain (order = first-enabled outermost),
     `system_prompt_suffix` values concatenate, `history_policy` set by
     two different optimizations at once is a raised
     `ConflictingOptimizationsError`, not a silent pick-a-winner.
   - `cli_args.py`: `--enable NAME`, repeatable AND comma-separated
     (both `--enable a,b` and `--enable a --enable b` work) - covers
     "enable just one" and "enable a combination" equally naturally.
   - `_AVAILABLE_OPTIMIZATIONS` in `cli.py` starts **empty** - this
     session only built the pattern, not any real optimization yet.
     Conversation summarization (next) will be the first real one.
4. AGENTS.md: new "Token/cost tracking" section, and the real
   deliverable - "How to add a new optimization" - a step-by-step guide
   (which hook to pick, a code sketch for each of the 3 hooks, how to
   register, how to prove it with before/after `/usage`, how combining
   optimizations behaves) written so it's usable standalone, the same
   way "How to add a new tool" and "Adding a new LLM provider" already
   were before this session.

**Verified manually, each piece before moving to the next:**
- Cost math by hand (twice, exact match) - see above.
- Fail-fast on an unpriced model (`AGENT_MODEL=some-unpriced-model` ->
  clean error, exit code 1) and on an unregistered `--enable` name
  (same).
- `/usage` at zero messages (no divide-by-zero/edge-case issue) and
  after multi-tool-call turns.
- Full regression after wiring `HistoryPolicy` into `AgentLoop`: a
  5-tool-call chained request behaves identically to before, and the
  startup banner/`/usage` correctly show "optimizations: none" with
  nothing enabled.
- `OptimizationBundle.merged_with` unit-tested directly (5 scenarios:
  empty resolve, unknown name, wrapper composition order, prompt-suffix
  concatenation, history_policy conflict) before wiring it into
  anything else.
- Re-ran the full README "first demo" flow (list -> create -> read ->
  edit -> write+run -> `/usage`) as one real session end-to-end before
  updating the README to match, same discipline as previous sessions -
  every documented example in this repo has actually been run, not
  guessed.

**Committed in small increments this session** (per explicit user
request) rather than one large commit at the end - see git log for the
6 separate commits, each independently working and tested before the
next began.

**Immediate next steps, in the order the user wants them:**
1. Benchmark runner (SWE-bench Lite subset, Docker-free) - still not
   built; was next before the AGENTS.md ask took priority.
2. Conversation summarization, as the first real
   `_AVAILABLE_OPTIMIZATIONS` entry and reference implementation for
   Krishna/KP to copy - validated against the benchmark runner once (1)
   exists, per the user's explicit reasoning: prove the pattern with
   real before/after numbers, not just working code.
3. Function calling/MCP comparison (user's second task, after
   summarization) - clarified this session: NOT "which one wins," but
   building an MCP-server version of one existing capability (e.g. file
   ops, which has an official reference MCP server to compare
   apples-to-apples against; or a real-world example like Jira) plus
   MCP *client* support (which the agent doesn't have at all today),
   run the same task both ways, and hand attendees a repeatable way to
   assess which approach fits their own situation - not a blanket
   verdict.

---

## [2026-07-28] Built the benchmark runner - real, working, Docker-free

User asked "what next to build?" - per the priority agreed last session
(metrics -> benchmark -> summarization, benchmark comes before the
first real optimization so it can validate that optimization with real
before/after numbers), this session built the benchmark runner. Also
did a small prerequisite refactor first, and picked up one loose end
(AGENTS.md's optimization guide needed to point at something real - see
previous entry).

**Prerequisite refactor** (agent/factory.py, optimizations/available.py):
the benchmark runner needs to build an AgentLoop and resolve --enable
exactly like the interactive CLI does. Pulled `_build_agent` out of
cli.py into `agent/factory.py`'s `build_agent()`, and moved
`_AVAILABLE_OPTIMIZATIONS` out of cli.py into
`optimizations/available.py`'s `AVAILABLE_OPTIMIZATIONS` - both now
shared by cli.py and benchmark/report.py instead of cli.py owning
private copies. `cli_args.py`'s `parse_enabled_optimizations()` became
`parse_args()`, returning a `CliArgs(enabled_optimizations, benchmark)`
so `--benchmark` and `--enable` are parsed together. Verified: full
regression (identical interactive behavior), `--help` output correct.

**Picking real SWE-bench Lite instances, not guessing:**
- Queried the dataset directly via HuggingFace's datasets-server REST
  API (`datasets-server.huggingface.co/rows?dataset=...`) rather than
  pulling in the full `datasets` package as a dependency for a handful
  of rows.
- SWE-bench Lite's 300 test-split instances are dominated by
  django/sympy/matplotlib/sklearn (heavy scientific-computing repos with
  C-extension builds). Deliberately picked from the lighter repos
  instead - flask, requests, pylint, pytest - pure Python, no compiled
  extensions, to keep the Docker-free approach viable.
- Found the `swebench` PyPI package ships `swebench/harness/constants/
  python.py` - hand-maintained, per-repo-version pip package pins
  (SPECS_FLASK, SPECS_REQUESTS, SPECS_PYLINT, ...). Used **only this
  data**, not any Docker/harness code from that package - pip-installed
  it just to read the constants module as a data source.

**Actually verified 3 candidate instances end-to-end before writing any
task-runner code** (clone real repo, checkout base_commit, install pinned
deps in a plain venv, apply test_patch, confirm FAIL_TO_PASS tests
genuinely fail, apply the real gold patch, confirm they genuinely pass).
This surfaced real environment problems no amount of reading the spec
would have caught:
- flask-4045 needed Python 3.9 specifically, not just pinned packages -
  Python 3.12's stricter deprecation handling (`ast.Str` removal path)
  broke test collection outright. Used `uv python install 3.9` +
  `uv venv --python 3.9` to get an isolated old interpreter.
- flask-4045's own pinned `blinker==1.4` has a SyntaxError on a *modern*
  3.9 patch release (3.9.25) - an unescaped backslash in a docstring
  that only became a hard error in later 3.9.x point releases than
  existed when flask pinned it. Bumped to `blinker==1.6.2`.
- `greenlet==1.1.0` (also in flask's own lockfile) fails to build from
  source on this machine/Python combo - skipped it since it's unused by
  the 2 target tests.
- pylint-5859's `pytest-benchmark~=3.4` crashes on `pytest_configure`
  against a modern `py` package (`AttributeError: module 'py' has no
  attribute 'io'`) - not needed for the target test, disabled via
  `-p no:benchmark`.
- requests-3362 needed no extra pins at all beyond `pytest` - the
  simplest of the three, confirming the "pick lightweight repos" choice
  was right.

Ended up with exactly 3 fully-verified tasks (not 5) - each verification
took real, non-trivial effort, and 3 was the agreed lower bound. Task
data (problem statement, test patch, FAIL_TO_PASS/PASS_TO_PASS) stored
as plain files under `benchmark/data/<instance_id>/`, not inlined in
`tasks.py`, to keep the Python logic readable.

**Built `sandbox.py` / `runner.py` / `report.py`**, then ran the actual
agent against a real task - and found two real bugs by doing that,
not by inspection:

1. **First run: zero tool calls, agent just answered conversationally.**
   SWE-bench's `problem_statement` is the *raw* GitHub issue as
   originally filed - often phrased as a question ("am I misunderstanding
   something?"), not an instruction. Passed unwrapped, the agent
   reasonably treated it as something to discuss, not fix. Fixed with an
   explicit task-framing wrapper in `runner.py` (the issue text itself
   stays untouched, for fidelity) - after the fix, the agent immediately
   started exploring and editing.

2. **Second issue: hitting AGENT_MAX_ITERATIONS was being treated as
   automatic failure.** Original code: `except (LLMError,
   AgentLoopSafetyLimitError): return resolved=False` - skipping the
   test check entirely. But tool calls mutate the sandbox's files
   immediately, regardless of whether the loop ever converges to a
   final text answer - so an agent that made the *correct* fix and then
   burned its remaining iterations re-verifying it (in one observed
   case: with the wrong Python interpreter, since it forgot the sandbox
   has its own `.venv`) would be wrongly counted as failed. Fixed to
   only skip the test check for `LLMError` (genuinely unreachable
   model); `AgentLoopSafetyLimitError` now still runs the tests. Proven
   correct in the full run below, not just in theory: `psf__requests-3362`
   hit the safety limit but was still correctly marked RESOLVED, because
   the code on disk was actually right.

**Verified with a full, real `uv run coding-agent --benchmark` run (no
mocking, no shortcuts):**
```
Resolved: 2/3, 618,451 total tokens, $1.3578, 322.5s wall-clock
[FAIL] pallets__flask-4045      tokens=240,768 cost=$0.5331 time=105.8s
[PASS] psf__requests-3362       tokens=272,122 cost=$0.5927 time=157.0s
[PASS] pylint-dev__pylint-5859  tokens=105,561 cost=$0.2320 time= 59.6s
```
flask-4045's failure was also legitimate, not a harness bug: the agent's
fix only handled one of the two required behavior changes (blueprint
name validation, but not the route-decorator endpoint check) - a
genuine partial fix, correctly caught as not-fully-resolved. Also
confirmed `--benchmark --enable does-not-exist` fails fast before any
expensive sandbox setup runs (no registered optimizations yet).

**Two commits hung mid-write this session** from literal backticks in
the commit message being interpreted by zsh as command substitution
(stripped a few inline-code-quoted words from one message before I
caught it, then switched to writing the message to a temp file and
using `git commit -F` for the rest - more reliable for multi-line
messages with backticks/code references going forward).

Updated AGENTS.md: new "Benchmark" section (why the tasks never change,
why no Docker, the "add a 4th" policy, the two failure modes above),
plus fixed two stale references to `cli.py` private helpers that moved
during the factory/available.py refactor. Added a short README mention
for workshop attendees.

**Not yet done:** conversation summarization (the actual first
`AVAILABLE_OPTIMIZATIONS` entry) - next per the agreed order, now
unblocked since the benchmark exists to validate it against.

---

## Hybrid pre-generation router + post-generation cascade (`--enable hybrid-routing`)

Added a cost-optimizing routing layer as a single optimization, following
the survey "Dynamic Model Routing and Cascading for Efficient LLM
Inference". It combines difficulty-aware pre-generation routing with a
post-generation cascade: each outgoing `send()` is scored 0-1 for
difficulty using free/local features; easy calls go to a local free
Ollama cheap tier first; a deterministic AST quality gate checks the
cheap output and escalates to the powerful tier only on failure (or when
pre-classified hard).

**Wired entirely through existing extension points** — no new subsystem:
- `optimizations/hybrid_routing.py` — `build() -> OptimizationBundle(wrap_llm_client=...)`,
  plus `RoutingLLMClient` (the decorator) and a shared-tracker accessor
  `get_tracker()`. One-line registration in `optimizations/available.py`.
- `optimizations/routing/` (one responsibility per file): `features.py`
  (lexical signals), `router.py` (`score_difficulty` + a `predict()`
  upgrade seam for a future sklearn classifier), `quality_gate.py`
  (`ast.parse` of fenced ```python blocks — the meaningful cheap gate at
  the `send()` boundary, since the response here is usually tool calls,
  not a code file), `metrics.py` (`RoutingTracker`, mirrors `UsageTracker`).
- `llm/ollama_client.py` — new `LLMClient` over Ollama's OpenAI-compatible
  API, mirrors `openrouter_client.py` (same translation helpers), reuses
  the already-present `openai` SDK (no LiteLLM). Unreachable Ollama →
  clean `LLMError`, not a crash.
- `commands/metrics_command.py` — `/metrics`, mirrors `/usage`, registered
  in `cli.py` only when the flag is on. `cli.py` also prints a compact
  per-turn routing annotation (a turn spans many `send()`s, so it
  summarizes that turn's records rather than printing per-`send()`).
- `config.py` — added `AGENT_ROUTING_*` fields with new `_require_float`
  and `_require_bool` helpers; matching `.env.example` block.
- `metrics/pricing.json` — `ollama/qwen2.5-coder:7b` at $0/$0 (local =
  free; still needs an entry or the agent fails fast). Cost stays
  real-tokens × pricing, never estimated — no parallel cost path.
- `pyproject.toml` — `[dependency-groups] dev = [pytest, ruff]` (dev-only).

**Key repo-specific decision:** routing is scored per `LLMClient.send()`
(the `wrap_llm_client` boundary), NOT per user turn — the tool loop makes
many sends per turn. Features score the latest *user* text so all sends
in a turn route consistently.

**Fallbacks (demo never hard-fails):** Ollama down → escalate to powerful
(`cheap_error`); powerful key unset → cheap-only, gate still runs, no
escalation (belt-and-suspenders — `Config` already requires the key at
startup).

**Verified in the terminal (not just by reading code):**
- `uv run pytest` — 10/10 pass in `tests/test_hybrid_routing.py` (fake
  in-memory `LLMClient`s, no HTTP): easy→cheap+gate-pass, hard→direct
  (score ≥ threshold), invalid-python→`cheap_escalated`
  (`ast_valid=false`), unreachable-cheap fallback, no-key cheap-only,
  `/metrics` aggregation (escalation rate, gate pass rate, cost), and
  pre-existing `/usage` + registry untouched.
- `OllamaClient` hit the real local Ollama (`qwen3.6:latest`, since
  `qwen2.5-coder:7b` wasn't pulled) → real token counts (in=24, out=128).
- Unreachable base URL → clean actionable `LLMError`.
- App boots with `--enable hybrid-routing`; `/metrics` and `/usage` both
  render. Without the flag, `/metrics` is correctly unknown and behavior
  is unchanged.
- `ruff check` clean on all new/changed files.

**Note for whoever runs the live demo:** `ollama pull qwen2.5-coder:7b`
first (only `qwen3.6:latest` was present on this machine). Wrote
`README_ROUTING.md` (workshop-facing: why, ASCII diagram, terminal UX,
which two paradigms + why hybrid beats either alone, run steps, the
`:free` OpenRouter stopgap for testing escalation pre-license, and the
`predict()`/embedding upgrade hooks).

---

## Hybrid routing v2: configurable N-tier ladder, fixed scorer, stronger gate

Follow-up to the previous entry, after review questions exposed three
real weaknesses. All three are now fixed, with regression tests.

### 1. The difficulty scorer had a structural bug (worst of the three)

The original scorer leaned entirely on hardcoded keyword lists. Measured
it: a genuinely hard 61-word prompt (GraphQL resolver fan-out, connection
pool saturation, backpressure) using none of the listed keywords scored
**0.35** and was routed to the 7B local model. Worse, it was structural -
with zero hard-keyword hits the max achievable was LENGTH(0.35) +
FENCE(0.15) = **0.50, below the 0.55 threshold**, so such a request could
*never* reach the powerful tier regardless of difficulty.

Fix: added **vocabulary-independent** signals to `features.py` that need
no word list - `long_word_ratio` (words >= 9 chars, a proxy for technical
register) and `clause_count` (sentences + connectives = how many things
are being asked at once). Reweighted `router.py` so those three
vocab-independent signals sum to **0.70**, above any sane threshold;
keywords are now a precision boost, not the foundation. Same prompt now
scores 0.58 -> correctly routed. Easy prompts still score 0.00. Both
properties are locked in by tests (incl. an explicit assertion that the
vocab-independent ceiling exceeds the threshold).

Known remaining limit, documented rather than overfitted around: a short
(~20 word) conceptually-hard request still scores ~0.42 and starts cheap.
Tuning weights to catch it misfires on short-but-easy technical requests,
so that case is deliberately left to the gate.

### 2. Quality gate widened beyond "does the Python parse"

The gate is what catches pre-router misses, so it got five new
deterministic checks alongside `ast_valid`: `unterminated_code_fence`
(truncated output), `refusal`, `placeholder_code` (TODO stubs),
`missing_tool_arguments` (validated against the tool's own JSON schema,
which is available at the send() boundary), plus the existing
`empty_response`. All conservative by design - a false FAIL costs a real
paid escalation - e.g. a refusal phrase is ignored when the model also
produced code or called a tool.

### 3. Two hardcoded tiers -> a config-driven N-tier ladder

`RoutingLLMClient` was hardcoded to `_cheap` and `_inner`. Replaced with
an ordered ladder loaded from **`optimizations/routing/tiers.json`**
(new), mirroring how `pricing.json` is plain data: each tier has name,
provider, model, and `difficulty_ceiling`. Pre-routing = start at the
first tier whose ceiling covers the score; cascading = climb one rung on
gate failure, repeat. Adding a mid tier is now a data edit, no code
change. Validation is fail-fast (`InvalidTierConfigError`): ceilings must
ascend, names unique, last tier must be 1.0, non-`inner` tiers need a
model. Special provider `inner` = reuse the wrapped client
(AGENT_PROVIDER/AGENT_MODEL), so there's still no parallel POWERFUL_MODEL.

Supporting changes: `llm/factory.py` gained `build_provider_client()` for
arbitrary provider/model pairs and registered `ollama` (adding a provider
remains 3 small edits); `Config` gained `available_provider_keys` so a
second paid provider's key can be found without any module outside
config.py touching os.environ; `RoutingRecord` gained `tier` and `hops`;
`/metrics` gained an "Answered by tier" breakdown.

**Bug the new tests caught:** when a request escalated and the higher tier
passed, the record stored the *winning* tier's clean gate result -
erasing why it escalated at all. `_climb` now always reports the **first**
attempted tier's outcome, which is both the escalation reason and the
routing-relevant signal. Also documented that `gate_pass_rate` counts the
first tier attempted on every send (including direct-to-top ones), so it
measures the routing decision, not just the cheap model - the metrics
test asserts the resulting 66.7%, not a hand-waved number.

### Verified in the terminal

- `uv run pytest` - **32/32 pass** (was 10), incl. 3-tier stepwise
  escalation, tier-skipping, 4 parametrized invalid-ladder cases, and one
  test per new gate check.
- **Real end-to-end with live Ollama**: pointed the cheap tier at the
  pulled `qwen3.6:latest` and ran an actual turn. The local model handled
  the whole thing - 3 sends including `list_files` + `write_file` tool
  calls - at **$0.0000**, paid tier never touched (the dummy API key was
  never even used). Confirms the new `missing_tool_arguments` check
  doesn't false-positive on real tool calls.
- Verified the 3-tier ladder loads and routes (0.1->cheap, 0.5->mid,
  0.9->strong) purely from the data file, and that a tier model missing
  from pricing.json fails fast at startup with an actionable message.
- REPL boots with the flag, without it (`/metrics` correctly unknown,
  `/usage` unchanged), and combined with `conversation-summary`.
- `ruff check` clean on all files this task touched. Pre-existing lint
  findings in `benchmark/`, `agent/conversation.py`, and `tools/bash.py`
  were left alone - not part of this task.
- Cleaned up after the live run (removed the file the agent wrote,
  restored `tiers.json` and `pricing.json`).

**Note:** `qwen2.5-coder:7b` still isn't pulled on this machine (only
`qwen3.6:latest`); run `ollama pull qwen2.5-coder:7b` before the demo, or
point tiers.json at a model you have. README_ROUTING.md updated
throughout, including an explicit note on why Terraform is the wrong tool
for this config and what is/isn't configurable without code changes.

## [2026-08-05] /usage made model-aware: per-model tokens + correctly priced cost

### Problem

With `--enable hybrid-routing`, `/usage` always showed
`Provider/model : anthropic / claude-sonnet-5` and priced the whole
session at the configured model's rate - even when the routing ladder
served calls with `ollama/qwen2.5-coder:7b`. Root cause: `LLMResponse`
carried no model info, so `UsageTracker` merged all tokens into one
total and `UsageCommand` hardcoded `Config.model` for both display and
cost. The routing wrapper knew the answering tier (`LiveTier.model`) but
recorded it only into its separate `RoutingTracker` (`/metrics`). The
benchmark report had the same bug (`report.py` priced all usage at
`config.model`).

### What changed

- `llm/base.py`: `LLMResponse` gains `model: str = ""` - the exact
  pricing.json key of the model that served the call. Default "" only so
  fake clients keep working; every real client sets it.
- All three clients set it: Anthropic/OpenRouter use `self._model`;
  OllamaClient keeps the original prefixed string (`ollama/...`) in a new
  `self._model_id` since it strips the prefix for the API call but
  pricing.json is keyed on the prefixed form.
- `hybrid_routing.py`: `RoutingLLMClient.send()` stamps the answering
  tier's model onto the returned response via `dataclasses.replace`.
- `metrics/usage.py`: `UsageTracker` gains `by_model` / `calls_by_model`;
  `record_llm_call(usage, model)` now requires the model. Both callers
  updated (`agent/loop.py`, `optimizations/conversation_summary.py` -
  the summarizer's own calls are attributed too).
- `commands/usage_command.py`: shows `Configured` + `Models used` lines,
  a `Per model:` block (calls, tokens, cost each - only when >1 model),
  and total cost summed per model at each model's own rate. A defensive
  ""-bucket (client that didn't report a model) is attributed to the
  configured model.
- Benchmark: `TaskResult` gains `usage_by_model`; `report.py` prices per
  model (summary + per-task) and prints a per-model block when more than
  one model was used, so routed cheap-tier tokens are no longer billed at
  the configured model's rate.
- Tests: routed responses assert `response.model`; new tests for
  per-model accumulation and for `/usage` pricing each model at its own
  rate (1M free ollama tokens + 1M claude input tokens = $2.0000, not
  $12+ at claude rates).

### Deliberately out of scope

Failed escalation attempts' tokens (cheap tier answers, gate rejects,
ladder climbs) are still not counted anywhere - `_climb()` discards the
failed response, and recording it would need the `UsageTracker` injected
into the wrapper (an `OptimizationBundle` API change). Pre-existing gap,
noted, not widened.

### Verified

- `uv run pytest` - 34/34 pass (was 32; 2 new).
- Rendered `/usage` manually for a mixed-model session (per-model block,
  cost $0.0018 = claude tokens only) and a single-model session (output
  shape unchanged apart from the `Configured`/`Models used` split).

### Follow-up (same session)

The `Configured` line still only showed `anthropic / claude-sonnet-5`
even with routing enabled - misleading next to a `Models used` line
listing ollama. `UsageCommand` now accepts optional
`configured_models`; cli.py passes the routing ladder (cheapest first,
'inner' resolved to `config.model`) when hybrid-routing is enabled, so
the header reads
`Configured : ollama/qwen2.5-coder:7b -> claude-sonnet-5 (routing ladder)`.
Plain sessions keep the `provider / model` form. The routing setup block
in cli.py moved above command construction so the ladder is known when
`/usage` is built. 34/34 tests still pass.

### Follow-up 2 (same session): per-turn summary for non-routing modes

hybrid-routing sessions got a per-turn annotation line (path, model,
difficulty, gate, latency, cost) but the base agent printed nothing
after a turn. cli.py now prints a mode-appropriate line after every
turn:

- base agent: `↳ <model> · <n> LLM calls · <tokens> tokens ·
  <wall-clock>ms · $<cost>` (new `_format_turn_summary`, computed by
  diffing UsageTracker.by_model before/after the turn - same snapshot
  pattern the routing summary already used; cost priced per model, no
  estimates)
- routing sessions keep their existing richer line; difficulty/gate
  fields stay routing-only.

AGENTS.md ("Token/cost tracking") now documents the convention: a new
optimization that introduces its own mode with its own signals should
add its own per-turn line in cli.py, showing only fields that apply to
that mode. 34/34 tests still pass; line rendering verified manually,
including the no-LLM-call case (prints nothing).

## [2026-08-06] Unified models.yaml: provider/model config, cheap->high routing ladder, per-model metadata, session cost cap

### Why

Workshop needs: (1) provider + models driven from one YAML instead of
scattered env/JSON, (2) a cheap->high OpenRouter routing ladder that fits
a $100 OpenRouter budget across ~60-70 participants (90 min, ~$1 each) plus
our own testing, (3) per-model metadata so the pre-routing phase has
context. User was away and delegated the decisions.

### What changed (single source of truth)

`src/coding_agent/models.yaml` (NEW) now drives everything about *which*
models are used - replacing both `metrics/pricing.json` and
`optimizations/routing/tiers.json` (both deleted) and the env-only
provider/model defaults. Four sections: `default:` (base provider/model/
max_tokens), `session_cost_cap_usd:`, `models:` (catalog = price +
metadata per model), `routing:` (ladder + gate/ollama settings). Loaded &
validated by `models_config.py` (NEW). Secrets still live only in `.env`;
`AGENT_PROVIDER/MODEL/MAX_TOKENS/SESSION_COST_CAP_USD` are now optional
overrides of the YAML defaults.

- `pricing.py`: `PricingTable.load()` reads the `models:` catalog (was
  pricing.json). `load(path=)` added for tests.
- `tiers.py`: `load_tiers()` reads `routing.tiers` from models.yaml; a
  tier names only a `model` and its provider is resolved from the catalog
  (still supports explicit `provider`, incl. `inner`). Validation intact.
- `config.py`: provider/model/max_tokens/cost-cap/routing settings default
  from models.yaml, env overrides. Dropped reference-only
  `routing_cheap_model` / `routing_difficulty_threshold`.
- Cost cap: `metrics/cost_guard.py` (NEW) `CostGuard`; `AgentLoop` gets an
  optional guard and, before each send, stops with a notice once the
  session's estimated cost crosses the cap. `build_agent(pricing=...)`
  wires it for the REPL; benchmark passes no pricing so it stays uncapped
  (a controlled measurement shouldn't be cut off mid-task).
- `/usage`: now shows the cost cap (`$X / $cap cap`) and a per-model
  strengths note from the catalog metadata. cli passes catalog metadata +
  cap in.
- Docs: AGENTS.md (module map + new "Model config" + cost-cap sections),
  README_ROUTING.md, .env.example all updated. Added pyyaml dependency.

### The routing ladder chosen (from live openrouter.ai pricing, per 1M tok)

| tier | model | $ in / out | difficulty_ceiling |
|---|---|---|---|
| cheap | deepseek/deepseek-v4-flash-0731 | 0.09 / 0.18 | 0.45 |
| mid   | thinkingmachines/inkling-small  | 0.45 / 1.20 | 0.75 |
| high  | qwen/qwen3.8-max                | 2.00 / 6.00 | 1.00 |

Base default (routing off) = the mid model. Catalog also keeps
claude-sonnet-5 / anthropic/claude-sonnet-5 / ollama/qwen2.5-coder:7b for
non-workshop setups + tests.

### Budget math (why this fits $100)

Rough per-participant 90-min session ~= 40 turns x 8 LLM calls x (4k in +
400 out) ~= 1.28M input / 128k output tokens.
- With routing (70% cheap / 20% mid / 10% high): ~$0.58/participant ->
  ~$40 for 70 people. Fits $100 with testing headroom.
- Without routing (all high): ~$3.33/participant -> ~$233. Over budget -
  which is exactly the lesson the workshop demonstrates.
- The $1.00 session cost cap is the hard guarantee: <= ~$70 worst case for
  70 participants even if everyone hammers the high tier.

### Metadata & pre-routing (direct answer to the user's question)

There was NO per-model metadata before; pre-routing decided purely on the
difficulty score vs. `difficulty_ceiling`. Metadata (description,
context_window, strengths, good_for_difficulty) is now STORED in the
catalog and surfaced in `/usage`, but is NOT yet consumed by the router -
capability-aware routing is now a code change away, not a data-gathering
exercise. Left as a deliberate follow-up to keep this change reviewable.

### Verified

- `uv run pytest` - 46/46 pass (was 34; +12: new tests/test_models_config.py
  for YAML pricing/ladder/metadata/cost-guard + loop-stops-at-cap, plus a
  5th invalid-ladder case).
- Manual: ladder loads from YAML with provider resolved from catalog;
  `/usage` renders the ladder, per-model breakdown with strengths, and
  `$… / $1.00 cap`; `Config.from_env()` boots (env provider/model override
  + yaml max_tokens/cap defaults).
- `ruff check` clean on all files this task touched (the 5 remaining
  findings are pre-existing: bash.py, conversation.py, benchmark/).
- pricing.json and tiers.json deleted; no code references them (remaining
  hits were doc comments, updated).

### Follow-ups (not done, on purpose)

- Wire metadata into the routing decision (capability-aware pre-routing).
- Failed escalation-attempt tokens still counted only in RoutingTracker,
  not /usage (pre-existing gap).
- Prices are as-listed today; verify slugs/prices before the workshop -
  they're a one-line YAML edit each.

---

## [2026-08-10] Colab workshop notebook (draft)

Added `notebooks/optimizing_llm_apps.ipynb` - the hands-on notebook for the
"Optimizing LLM-Powered Applications" workshop. It clones this repo in
Colab, installs deps, takes an OpenRouter key, then walks attendees from the
base agent through each optimization, measuring real tokens/cost each step.

### How it drives the agent

Does NOT shell out to the REPL. It drives the agent IN-PROCESS, the same way
`benchmark/runner.py` does: `build_agent(config, usage_tracker, bundle,
pricing=...)` + `agent.run_turn(prompt)`. This is what lets it capture exact
per-run tokens/cost. `/usage` is reproduced via `UsageCommand(...).run()`
and routing `/metrics` via `RoutingMetricsCommand(...).run()` - no new code
in the repo, the notebook just instantiates the existing commands.

Two harness helpers in the notebook: `WorkshopSession(optimizations=[...])`
(wraps a session, `.ask()`, `.usage_report()`, `.routing_report()`,
`.metrics()`) and `run_scenario(label, opts, prompts)` + `compare(baseline,
*others)` (runs the shared prompt set, prints a pandas table with % saved).
Optimization names are auto-discovered from `AVAILABLE_OPTIMIZATIONS`.

### Decisions (user was unavailable; made autonomously)

- Clone URL `https://github.com/shrijayan/coding-agent` (main).
- Model slugs treated as possibly-placeholder: added a Step-5 connectivity
  ping that fails loudly before the demos if a slug/key is wrong.
- API key: Colab Secrets (`userdata`) first, else hidden `getpass`.
- Covered the two REAL optimizations (conversation-summary, hybrid-routing)
  + combined; added a "coming soon" section for the not-yet-built ones.
- Shared `DEMO_PROMPTS`: a 5-turn calculator build (multi-turn so summary
  triggers past the threshold; routine edits so routing sends them cheap).
  Same prompts for every config so before/after is apples-to-apples.
- Sets required env in-notebook (AGENT_PROVIDER=openrouter, iterations,
  bash timeout, summary thresholds 8/4). Uses a `playground/` scratch dir
  (agent tools act on cwd; models.yaml is package-relative so chdir is safe).

### Verified

- Built the .ipynb from a throwaway `json.dump` builder (deleted after);
  valid notebook JSON, 38 cells, nbformat 4.
- Offline smoke test (throwaway, deleted): constructed a WorkshopSession for
  all four combos ([], summary, routing, both) under a dummy key - imports
  resolve, sessions build, `/usage` + `/metrics` render, no network hit.

### FOR THE NEXT SESSION (adding a new optimization)

When prompt-caching / context-window-opt / agent-loop-prevention land:
implement + register one line in `optimizations/available.py`, then in the
notebook add a concept markdown cell + a `run_scenario("+ name", ["name"],
DEMO_PROMPTS)` + `compare(baseline, ...)` cell, and add it to the `runs`
list feeding the scoreboard. No harness changes needed. (Also noted in repo
memory: `/memories/repo/workshop-notebook.md`.)

### Follow-ups (not done, on purpose)

- Notebook not executed end-to-end against a live model (no key here, and
  the OpenRouter slugs may be placeholders) - the connectivity cell is the
  guard for that. Run it once with a real key before the workshop.
- Consider a "Open in Colab" badge in README pointing at this notebook once
  its GitHub path is final.

## [2026-08-10] Conference deck: modular offline HTML slides (ThoughtWorks / XConf 2026)

Added `presentation/` - a self-contained, offline HTML slide deck for the
"Optimizing LLM-Powered Applications" workshop, branded to the XConf 2026 /
Thoughtworks template (extracted from `xconf_ppt.pdf`: dark teal #003d4f,
coral #f2617a, amber/green/purple/teal accents, Bitter serif headings +
Inter body, `/thoughtworks` wordmark, footer + slide numbers, the chrome "X"
motif rebuilt in CSS). Built on reveal.js 5.1 (vendored, no CDN) so it runs
by double-clicking `presentation/index.html` - no server, no network.

### Structure (modular, one file per slide)

- `index.html` - shell: persistent chrome (HUD, logo, footer) + `<script>`
  includes. The order of the `slides/*.js` tags IS the deck order.
- `css/` - `theme-thoughtworks.css` (brand tokens + reveal overrides),
  `layouts.css` (cover/separator/split/cards/icon-rows/recap components),
  `hud.css`, `animations.css` (the two data-state showcases).
- `js/` - `components.js` (`TW.icon()` inline-SVG set), `hud.js` (the
  top-right TOKENS + COST meter with number tweening + delta chips),
  `deck.js` (assembles registered slides into reveal, then a single
  declarative `update()` keeps HUD / visual `[data-state]` / chrome in sync
  from whichever fragments are visible - so fwd AND back nav stay correct).
- `slides/00..90-*.js` - each calls `Deck.add({ id, html, dark, hideHud,
  tokens, cost, notes })`. 27 slides: presenters -> title -> agenda -> base
  agent (loop, cost tracking, notebook) -> the 5 techniques -> recap ->
  "add your own" -> dark thank-you.

### The signature bits (from the brief / voice note)

- Persistent top-right **token + cost HUD**, always on during technical
  slides. Fragments carry `data-tokens` / `data-cost` / `data-hint`; the HUD
  tweens to them (tokens can drop, cost only climbs - session-cumulative).
- **Summarization "lab"** (slide 9): conversation history visibly collapses
  into a running-summary card while the HUD's tokens crash ~74% and cost
  ticks up for the (honestly counted) summarize call - exactly the
  "long text -> summarized -> added to context, tokens down / cost up" ask.
- **Routing ladder** (slide 16): a difficulty gauge + cheap/mid/high rungs
  that light per example, incl. the quality-gate cascade. Both showcases are
  driven purely by a `[data-state]` attribute set from visible fragments.

### Honesty / grounding

Two techniques are marked LIVE (conversation-summary, hybrid-routing - real
`--enable` flags, code shown from `conversation_summary.py` /
`hybrid_routing.py` / `models.yaml`); three are marked BUILDING (prompt
opt+caching, context-window, loop-prevention) with design + where-they-plug-in
(the `OptimizationBundle` hooks) rather than pretending they're done. Notebook
cues point at the real headings in `notebooks/optimizing_llm_apps.ipynb`
("Baseline...", "Optimization 1 - Conversation summarization", "Optimization
2 - Model routing"). Presenter names/roles are `Presenter One/Two/Three`
placeholders - find-and-replace in `slides/00-intro.js` (+ `90-closing.js`).

### Verified

- All `js/`+`slides/` pass `node --check`.
- Headless Chrome (puppeteer-core against installed Chrome, throwaway harness
  in TMP) loaded the deck from `file://`: 27 slides, reveal ready, HUD wired,
  7 font faces loaded, **0 console/page errors**; stepped the summarize + the
  routing-cascade fragments and confirmed HUD/state stay in sync on fwd/back;
  screenshotted every slide for a visual pass. Found + fixed three real bugs:
  `TW.icon()` returned raw paths (never wrapped in `<svg>`); dark slides had
  no dark background (white-on-white) - now `data-background-color`; sections
  weren't full-height so covers/separators collapsed - now fixed `.pad`
  height. Fonts vendored as latin-subset woff2 (Bitter + Inter) under
  `vendor/fonts/`.

### Follow-ups (not done, on purpose)

- Real presenter names/photos (placeholders left, avatars are CSS gradients).
- Repo URL on the closing slide is `github.com/<your-org>/coding-agent`.
- When the 3 BUILDING techniques land, flip their pills to LIVE and add a
  notebook cue + code slide (same pattern as summarization/routing).

---

## [2026-08-11] Cache-friendly prompt construction (`--enable cache-friendly-prompts`)

New optimization: a deterministic, layered prompt-construction pipeline that
maximizes prompt-cache reuse across any OpenRouter-supported model, provider
agnostically (no `cache_control` / vendor APIs in the core). Plugs in through the
same first-class hook as routing - `OptimizationBundle(wrap_llm_client=...)` -
so the agent loop and every provider client are untouched.

### What it does

On every `LLMClient.send()` the wrapper (`optimizations/cache_friendly.py`)
rebuilds the outgoing prompt through a small, reusable pipeline and forwards a
deterministic version of it to the wrapped client:

- **`prompt_cache/layers.py`** - `PromptLayer` + `LayerTier` (STABLE /
  SEMI_STABLE / DYNAMIC). Categorization per the brief: STABLE = system prompt,
  tool/MCP defs, guidelines, repo metadata; SEMI_STABLE = summary, active files,
  task context; DYNAMIC = latest message, tool results, logs.
- **`prompt_cache/serializer.py`** - `PromptSerializer`: canonical JSON
  (`sort_keys`, compact separators, `ensure_ascii=False`), whitespace
  normalization, SHA-256 of a section. Identical content -> byte-identical output.
- **`prompt_cache/builder.py`** - `PromptBuilder` + `BuiltPrompt`: turns raw
  `send()` inputs into ordered layers (stable-before-dynamic guaranteed by a
  stable sort), sorts tools by name + recursively key-sorts schemas, normalizes
  the system string, and **memoizes the stable section** so it's reused, not
  regenerated, until system/tools actually change (`stable_recomputes` proves it).
- **`prompt_cache/metrics.py`** - `PromptCacheTracker` + `PromptCacheRecord`
  (mirrors `routing/metrics.py`): stable-prefix hash + size, per-tier bytes,
  prefix **reuse %** (longest common canonical-byte prefix vs the previous send /
  current size), cache-friendly ratio (stable bytes / total), and real input
  tokens.
- **`prompt_cache/provider_adapter.py`** - `ProviderCacheAdapter` Protocol +
  `NoOpProviderCacheAdapter` default + `PreparedRequest`. The pluggable seam: a
  future Anthropic `cache_control` adapter drops in here (constructor-injected)
  without touching builder/serializer/core.

### Token honesty

Followed the hard rule (never estimate tokens): the only token figure is the
provider's **real** `usage.input_tokens`; stable-prefix length, reuse %, and
cache-friendly ratio are deterministic **byte** measurements, never a tokenizer
guess. Messages are never reordered (only STABLE layers are canonicalized), so
correctness and the real provider cache prefix are preserved.

### Surfaced

- `/cache` slash command (`commands/cache_command.py`, mirrors `/metrics`):
  session stable-hash stability, avg prefix reuse, cacheable ratio, latest
  byte breakdown, real input tokens.
- Per-turn CLI line `_format_cache_summary` in `cli.py` (its own mode line,
  printed in addition to the routing/plain line since it composes with routing).
- One-line registration in `optimizations/available.py`. `build()` is
  zero-config (no new required env vars), so fail-fast startup is unaffected.

### Presentation + notebook

- New slide module `presentation/slides/35-cache-friendly-prompts.js` (sep ->
  layered-stack concept + reuse bignum -> builder/serializer/seam how -> notebook
  cue), registered in `index.html` after 30, ThoughtWorks theme classes reused.
  Slide 30's plan callout flipped from "building now" to point at this now-live
  sibling technique.
- Notebook: new "Optimization 3 - Cache-friendly prompt construction" section
  (concept md + `run_scenario` + `compare` + a `/cache` report cell) plus a
  `cache_report()` method on `WorkshopSession` (mirrors `routing_report()`);
  `opt_cache` added to the combined `compare(...)` and the scoreboard `runs`
  list; "Coming soon" prompt-caching bullet updated to reflect the shipped
  groundwork.

### Verified

- New suite `tests/test_prompt_cache.py` (21 tests): determinism across
  builders, tool-order + dict-key-order independence, whitespace normalization,
  stable-before-dynamic invariant, stable hash unaffected by conversation growth,
  no dynamic ids in the stable prefix, stable-section reuse (memo) + recompute on
  change, prefix reuse growth, tracker aggregates, no-op adapter pass-through,
  wrapper forwards normalized prompt + records real tokens, `build()` bundle
  wiring, `/cache` command, serializer canonicalization.
- Full suite: 67 passed. `ruff check` clean on all new/changed files (the 5
  remaining repo lint hits are all pre-existing, in files not touched here).
- `node --check` passes on the new + edited slide JS; notebook re-parses as
  valid JSON with 0 python-cell syntax errors; registry resolves
  `cache-friendly-prompts` and composes with `conversation-summary` /
  `hybrid-routing` without conflict.

### Follow-ups (not done, on purpose)

- The actual provider-side `cache_control` adapter (Anthropic et al.) - the seam
  is in place (`ProviderCacheAdapter`), but no concrete adapter ships yet.
- End-to-end run against a real OpenRouter key (needs a key); logic is covered
  by in-memory fakes in the test suite.

---

## [2026-08-11] Ollama as a keyless base provider (offline testing) 

Goal: let someone without an OpenRouter key test prompt caching and hybrid
routing today, fully offline on local Ollama models, WITHOUT changing the
committed default (still `openrouter` in models.yaml) - so nothing has to be
reverted once the key arrives. Ollama already existed as a *routing-tier*
provider (`OllamaClient`, `build_provider_client`); this promotes it to a
selectable *base* provider and gives routing a local ladder.

What changed:
- `models.yaml`:
  - New `provider_models:` block (provider -> base model). Used only when
    `AGENT_PROVIDER=<name>` selects a provider listed here AND `AGENT_MODEL`
    is unset, so `AGENT_PROVIDER=ollama` picks up `ollama/qwen2.5-coder:7b`
    without also setting `AGENT_MODEL`. `default:` still owns the committed
    default provider/model (openrouter).
  - Two new catalog entries: `ollama/llama3.1:8b`, `ollama/qwen2.5-coder:14b`
    (both free, $0.00, with metadata), alongside the existing 7b entry.
  - New `routing.ollama_tiers` ladder (cheap 7b / mid llama3.1:8b / high 14b) -
    an alternate to `routing.tiers`, same shape/rules.
- `models_config.py`: `load_provider_models(raw)` (optional block -> map).
- `optimizations/routing/tiers.py`: `load_tiers(path=None, *, provider=None)`.
  When `provider == "ollama"` and `routing.ollama_tiers` exists, that ladder is
  used; every other provider (and `provider=None`) uses `routing.tiers`. The
  mapping lives in one place (`_PROVIDER_TIERS_KEYS`) so both call sites agree.
- `config.py`: `ollama` is now a valid base provider (`_LOCAL_PROVIDERS`), and
  keyless - `_resolve_api_key` returns `""` for local providers instead of
  requiring an API key. Base model resolves via
  `AGENT_MODEL` -> `provider_models[provider]` -> `default.model`.
- `llm/factory.py`: `build_llm_client` builds an `OllamaClient` (base URL from
  `routing.ollama_base_url`, no key) when the base provider is local.
- `cli.py` + `hybrid_routing.build_live_tiers`: both call
  `load_tiers(provider=config.provider)` so the pricing check and the live
  ladder pick the same (ollama) tiers.
- `.env.example`: documented `AGENT_PROVIDER=ollama` (keyless) + the ollama
  base-model line.

How to run (fully offline, no key). Note the user's personal `.env` pins
`AGENT_MODEL=claude-sonnet-5`, and an explicit `AGENT_MODEL` correctly wins
over `provider_models`, so pass an ollama model (or blank it) when switching:
- Base / prompt caching:
  `AGENT_PROVIDER=ollama AGENT_MODEL=ollama/qwen2.5-coder:7b uv run coding-agent
   --enable cache-friendly-prompts`
- Hybrid routing (local ladder):
  `AGENT_PROVIDER=ollama AGENT_MODEL=ollama/qwen2.5-coder:7b uv run coding-agent
   --enable hybrid-routing`
Needs `ollama serve` running and the three models pulled.

Verified: full suite 67 passed (unchanged - all existing `load_tiers()` calls
default to `provider=None` -> the openrouter ladder). Config smoke test with
`AGENT_PROVIDER=ollama`: provider=ollama, api_key='', base client=OllamaClient,
base + all three ladder models priced, and `load_tiers()` with no provider
still returns the openrouter ladder.

### Follow-ups (not done, on purpose)

- No runtime `/provider` slash command - the user chose startup selection only
  (a mid-session switch is moot here since the app can't start without the
  selected provider's key, and ollama is keyless so it starts fine).
- No end-to-end run against a live Ollama (sandbox blocks localhost:11434);
  wiring verified via config/ladder resolution + the existing in-memory tests.

### [2026-08-11] Follow-up - reconciled ollama_tiers with pulled models + live E2E

Sandbox was lifted, so `ollama list` finally worked and the models chosen up
front (`llama3.1:8b`, `qwen2.5-coder:14b`) weren't actually pulled - only
`qwen2.5-coder:7b` and `qwen3.6:latest` (plus embedding-only `bge-m3` /
`nomic-embed-text`, unusable for chat). Corrected `models.yaml` to reality:
- Catalog now lists the real chat models (`ollama/qwen2.5-coder:7b`,
  `ollama/qwen3.6:latest`, and `ollama/llama3.1:8b` once the user pulled it).
- `routing.ollama_tiers` is cheap `qwen2.5-coder:7b` (0.45) / mid `llama3.1:8b`
  (0.75) / high `qwen3.6:latest` (1.0).

Verified live against the running Ollama (not just wiring): base+cache turn
answered on `qwen2.5-coder:7b` with the cache line printed; routing turn scored
difficulty, routed cheap, quality gate PASS, `/metrics` correct, no skipped
tiers; the mid client (`llama3.1:8b`) returns real token usage on a direct
send. Full suite still 67 passed.

### [2026-08-11] REPL colors + always-visible per-send routing detail

Two cli.py-only presentation changes (no behavior/logic change elsewhere):
- Color scheme (ANSI, `cli.py`): agent answer green, user prompt/input white,
  every auxiliary line yellow (turn/routing/cache summaries, tool-call lines,
  startup warnings, and all slash-command output incl. /usage, /metrics,
  /cache), errors red. Gated on `sys.stdout.isatty()` (`_USE_COLOR`) via tiny
  `_seq()`/`_color()` helpers, so piped/redirected output and the benchmark
  stay escape-code-free. The white input color is opened on the `you>` prompt
  and reset right after `input()` returns.
- Routing summary now always shows difficulty + answering model, even on
  multi-send (tool-loop) turns. `_format_single_record` was refactored into
  `_routing_detail` (the marker-less detail body), reused by both the
  single-send line and a new numbered per-send breakdown under a header
  roll-up:
    ↳ routing: 2 sends · 2 direct_powerful · 14497ms · $0.0000
        1. direct_powerful · mid/llama3.1:8b · difficulty 0.65 · 8200ms · $0.0000
        2. direct_powerful · mid/llama3.1:8b · difficulty 0.65 · 6297ms · $0.0000
  (Prompted by confusion that the old multi-send roll-up hid difficulty/model.
  Reminder: `direct_powerful` = pre-router skipped the cheap tier and started
  higher, NOT necessarily the top tier.)

Verified: `_format_routing_summary` renders the header + numbered per-send
lines; `_color` emits the right ANSI codes when forced on; ruff clean on
cli.py; full suite 67 passed.

### [2026-08-11] Presentation revamp: XConf branding, auditorium readability

Full pass over `presentation/` to align the deck with the official
Thoughtworks XConf template and make it readable from the back of a large
auditorium (presentation-only change; no agent code touched):
- Official palette applied exactly (Mist #EDF1F3, Onyx #000000, Flamingo
  #F2617A, Wave #003D4F, Turmeric #CC850A, Jade #6B9E78, Sapphire #47A1AD,
  Amethyst #634F7D) in `css/theme-thoughtworks.css`; XConf logo assets
  (`assets/xconf-logo{,-white}.png`) in the persistent chrome, and the "X"
  sculpture image on the cover + every technique separator.
- Readability: bigger base type, concept-first slides; all large code panels
  replaced with flow diagrams / icon rows / callouts (`agent-loop`, `cf-how`,
  `build-your-own`, ...). Dense slides split instead of shrunk.
- Animations simplified: deck-wide fade transition, no per-bullet fragments
  on concept/theory slides; step-by-step fragments retained ONLY on the
  optimization showcase slides (sum-lab, pc-concept, cf-concept,
  route-ladder, cw-concept, lp-concept).
- HUD (Context tokens / Session cost) is now opt-in per slide (`hud: true`
  in deck.js) and appears only on those 7 optimization demos - hidden on all
  theory/branding slides.
- Fixed slide 9 (sum-lab) formatting and a systematic 52px vertical overflow
  on six `.slide-head + .split` slides: `.pad` is now a flex column and
  `.split` flexes into the remaining height instead of `height: 100%`
  (`css/layouts.css`).

Verified in the browser via scripted walk of all 31 slides: no console
errors, no broken images, zero overflow on every fully-revealed slide, HUD
visible only on the 7 demo slides, sum-lab/route-ladder state machines
correct forward AND backward.

---

## [2026-08-12] Notebook as a thin client: project-managed deps, BYO provider, standardized models

Refactored `notebooks/optimizing_llm_apps.ipynb` (and a little supporting
code) so the notebook behaves like a lightweight client for the repo
instead of duplicating its configuration.

Dependency installation (notebook Step 2):
- Removed the hardcoded `DEPS = [...]` pip list. The notebook now `cd`s
  into the clone and runs `pip install -e ".[notebook]"`, so ALL
  dependencies come from the repo's own `pyproject.toml`. When repo deps
  change, users just re-pull and re-run - nothing to edit in the notebook.
- Added a `[project.optional-dependencies] notebook` extra (pandas,
  matplotlib) in `pyproject.toml` so even the notebook-only viz libs are
  project-managed, not hardcoded. Regenerated `uv.lock` (`uv lock`);
  `uv sync --extra notebook` resolves cleanly.
- Verified the exact `pip install -e ".[notebook]"` command works with
  plain pip (Colab-like) in a fresh venv: PEP 660 editable install via the
  uv_build backend succeeds and `import coding_agent`/`pandas`/`matplotlib`
  all resolve.

Bring-your-own provider (notebook Steps 3-4, provider-agnostic):
- Collapsed the old "OpenRouter key" + "pin provider=openrouter" cells into
  ONE configuration cell exposing `PROVIDER` / `API_KEY` / `MODEL`. A
  `PROVIDERS` registry (env var, default model, tier presets, keys URL)
  makes adding a provider a one-entry change - openrouter and anthropic
  ship today. Key loading is provider-aware (explicit -> Colab secret named
  after the provider's env var -> env -> hidden prompt) and only the
  selected provider's key is required. The rest of the notebook reads
  `AGENT_PROVIDER`/`AGENT_MODEL` and adapts; no implementation code changes
  to switch providers.
- The underlying codebase already supported anthropic (config env-var map,
  llm factory builder, priced `claude-sonnet-5`). Added `anthropic:
  claude-sonnet-5` to `provider_models:` in `models.yaml` so
  `AGENT_PROVIDER=anthropic` with a blank `AGENT_MODEL` resolves to the
  right base model (mirrors the existing ollama pattern).

Standardized the three OpenRouter presets (requirement 4):
- `models.yaml` OpenRouter catalog + `routing.tiers` are now exactly:
  low `deepseek/deepseek-v4-flash-0731`, medium `minimax/minimax-m3`,
  high `z-ai/glm-5.2`. Replaced `thinkingmachines/inkling-small` (was the
  default + mid tier -> now medium `minimax/minimax-m3`, and the new base
  default) and `qwen/qwen3.8-max` (high -> `z-ai/glm-5.2`); removed the
  extra `anthropic/claude-sonnet-5` OpenRouter slug. Kept prices so tier
  ordering + the cost-cap test math ($2+$6=$8 on the high tier) still hold.
- Updated `tests/test_models_config.py` (two `qwen/qwen3.8-max` refs ->
  `z-ai/glm-5.2`) and `.env.example`'s example model list. Full suite green
  (67 passed).

hybrid-routing is OpenRouter/Ollama-based; the notebook's routing section
now notes anthropic users should skip that one cell (its tiers would be
unavailable) - the other optimizations are provider-agnostic.

Verified: all 67 tests pass; notebook JSON parses (40 cells); all 19 code
cells compile; Config.from_env resolves correctly for openrouter
(blank/low/high/custom-slug) and anthropic (blank -> claude-sonnet-5);
routing ladder fully priced.

### [2026-08-12] Presentation polish: vector logos, dark separators, auto choreography

Follow-up pass on `presentation/` after review feedback, drawing on the
"Engineering the Harness" XConf deck (dark Wave slides, huge Bitter serif,
minimal accent-bar dividers) as the reference:
- X sculpture now appears ONCE (the cover). All seven separators redesigned
  reference-style: dark Wave background, short accent bar (per-technique
  color via `--sep-accent`), huge centered serif title, pill + flag meta row.
- Logo resolution fixed at the root: the XConf logo only exists in the
  template PDF as a 600x317 raster, so both it and the /thoughtworks wordmark
  were vector-traced (uv + potracer) into 2-color SVGs with light/dark
  variants (`assets/{xconf,tw}-logo{,-white}.svg`). Chrome, cover and thanks
  slides now use them; the blurry PNGs were deleted. Gotchas: potracer traces
  the mask complement (invert before tracing), and the extracted XConf JPEG
  has flattened-black background so the wave letters must be isolated by
  blue-channel signature, not darkness.
- Slide 9 overlap actually fixed: `.sumlab`/`.ladder` needed
  `grid-template-rows: 100%` (implicit auto rows let the stream spill past
  the container into the caption), lab height 410px, stepline pushed down
  (26px margin) and given `min-height`.
- Auto entrance choreography in `animations.css`, keyed on `section.present`
  (no clicks): separators tell a bar->title->meta story; flow-diagram nodes
  walk left-to-right and the feedback arrow keeps cycling; icon rows, cards,
  stacks, presenter cards and recap rows stagger in; sum-lab chat messages
  land one-by-one; ladder shows gauge then rungs cheapest-first. Keyframes
  are from-only + `backwards` fill so entrances never fight state
  transitions or fragment visibility; `prefers-reduced-motion` disables all.

Verified via scripted walk of all 31 fully-revealed slides: no console
errors, no broken/missing assets, zero overflow, HUD gating still correct,
sculpture only on the cover, slide-9 stream clip 0-1px with clear gap to
the caption line.

### [2026-08-12] Recover lost cli.py colors + carry the palette into the notebook

Context: the previous session's last-turn cli.py edits (color scheme +
per-send routing breakdown) had been lost - they were uncommitted when the
working tree got reset to HEAD (aa74fb1), so git discarded them (stash only
held a uv.lock WIP). The Ollama integration and .env.example docs were safe
(committed). Re-applied the two lost cli.py changes verbatim (ruff clean, 67
passed).

Then extended the same palette to the workshop notebook
(`notebooks/optimizing_llm_apps.ipynb`) so participants get the readable
output too:
- Added `_c(text, code)` + ANSI constants in the harness cell. NOT gated on
  isatty (unlike cli.py) because Jupyter/Colab render ANSI even though stdout
  isn't a TTY.
- `WorkshopSession.ask`: prompt WHITE, `agent>` answer GREEN, tool lines +
  per-turn summary YELLOW; `usage_report`/`routing_report`/`cache_report`
  (i.e. /usage, /metrics, /cache) YELLOW; routing warnings YELLOW.
- `run_scenario`/`compare`: scenario header, run summary, and the text
  fallback table YELLOW (the pandas `display()` table is left native).
- Bonus correctness: notebook now calls `load_tiers(provider=self.config
  .provider)` so an Ollama-provider session picks the ollama ladder (harmless
  for the openrouter workshop default).

Caveat: `_WHITE` for the user prompt reads well on dark themes; on a light
Colab theme it's faint. Left as-is to match the terminal palette exactly, per
request. Verified: ast.parse of every code cell OK (13 `_c(` sites); ANSI
constants emit correct sequences.

### [2026-08-12] Swap the three OpenRouter presets to Gemma/Qwen/DeepSeek

New OpenRouter access policy allows only three models, so the ladder is now
(by capability): cheap `google/gemma-3.4b`, mid `qwen/qwen3.7-flash`, high
`deepseek/deepseek-v4-flash-0731`. Note DeepSeek moved cheap -> high (its old
role) and is the new base default; `minimax/minimax-m3` and `z-ai/glm-5.2`
were removed.

- `models.yaml`: rewrote the OpenRouter catalog block (reordered cheap->high),
  repriced per the new access policy - gemma 0.05/0.10, qwen 0.03/0.13,
  deepseek 0.08/0.252 (was 0.09/0.18) - refreshed each `metadata` description
  + strengths + good_for_difficulty for its new tier, pointed `routing.tiers`
  and `default.model` at the new slugs.
- Mirrored everywhere the presets are named: `.env.example` example list, the
  notebook (Step 3 config table, `PROVIDERS` registry default + presets,
  Optimization 2 routing description), and `README_ROUTING.md`'s ladder
  example.
- `tests/test_models_config.py`: cheap-tier slug assertion -> gemma, metadata
  lookup -> gemma, deepseek price math -> 0.08+0.252, and the two cost-cap
  tests' `z-ai/glm-5.2` refs -> deepseek (1M+1M = $0.332 still blows the $0.10
  cap). Full suite green (67 passed).

Note: exact slugs `qwen/qwen3.7-flash` and `google/gemma-3.4b` were inferred
from the access-policy display names using the same vendor/name-hyphenated
convention as the existing deepseek slug; pricing per user (in/out per 1M).


### [2026-08-12] Two new optimizations: `loop-guard` and `context-window`

Built the two techniques the slides (`50-context-window.js`,
`60-loop-prevention.js`) and the notebook's own "Coming soon" section had
flagged as in-progress, at the same quality bar as `cache-friendly-prompts`
(tracker + `/slashcommand` + per-turn CLI line + tests + notebook section).

Framework change first: `OptimizationBundle` only had 3 fields
(`history_policy`, `wrap_llm_client`, `system_prompt_suffix`). Added a 4th,
`extra_tools` (a `list[Tool]`, concatenated across optimizations - additive,
never a conflict like `history_policy` is), so an optimization can register
a new tool. Wired into `agent/factory.py`. Also extracted
`conversation_summary.py`'s tool_use/tool_result-pairing-safe cut logic into
a new shared `optimizations/history_utils.py` (`safe_keep_from`), since the
new pruning policy needed the exact same invariant.

**`loop-guard`** (`wrap_llm_client`): watches the tail of the conversation
for the same tool call failing with the same error, repeatedly. After
`AGENT_LOOP_GUARD_NUDGE_AFTER` identical failures in a row it injects a
corrective note before the next real call; after
`AGENT_LOOP_GUARD_HALT_AFTER` it skips calling the model entirely and
returns a synthetic zero-usage "loop detected, stopping" response instead
(`model=""`, the existing "no real model answered this" convention -
`UsageCommand._by_model` already folds that into the configured model and
skips it once its token delta is zero, so it doesn't crash or misprice
`/usage`). Complements the prompt-side instruction already in
`system_prompt.py` ("do not repeat the exact same call..."). `/loopguard`
reports counts only - no estimated "tokens saved by halting," since this
project never estimates.

**`context-window`** (`history_policy` + `extra_tools` +
`system_prompt_suffix`): two mechanisms, both about relevance over
compression.
1. `ContextPruningPolicy` replaces a stale, bulky tool-result output
   (outside the most recent `AGENT_CONTEXT_PRUNE_KEEP_RECENT_MESSAGES`
   window, over `AGENT_CONTEXT_PRUNE_MIN_CHARS_TO_PRUNE` chars) with a
   specific placeholder instead of resending it forever.
2. "Skills": `src/coding_agent/skills/*.md` (YAML frontmatter + body,
   parsed by the new `skills_library.py`) ship 3 example skills. Only the
   name+description menu goes in the system prompt; the full body only
   enters context via the new `load_skill` tool - progressive disclosure,
   same idea as Claude Skills.

Real bug caught during manual end-to-end smoke testing (not by the unit
tests, which only ever called `prepare()` once): `AgentLoop` calls
`history_policy.prepare()` again on every internal send() within a turn,
always against the same untouched, growing `Conversation.messages` - so the
pruning policy was re-"pruning" and re-recording the exact same old bulky
output on every subsequent call, massively overcounting `/context`'s
chars-removed stat as a session went on. Fixed by tracking already-recorded
`tool_use_id`s on the policy instance (mirrors how `ConversationSummaryPolicy`
tracks `_summarized_through` to avoid reprocessing) - added a regression
test (`test_repeated_prepare_calls_do_not_double_count_the_same_prune`) so
it can't silently regress.

Notebook: inserted "Optimization 4 - Agent loop prevention" and
"Optimization 5 - Context window optimization" sections between the
existing cache-friendly section and "Stack them", following the established
markdown-intro -> `run_scenario` -> `compare` -> `/x_report()` pattern;
widened the combined-stack and scoreboard cells to include both; trimmed
"Coming soon" to just what's still genuinely unbuilt (provider-side prompt
caching). Loop-guard's section is explicit that a well-behaved model should
show *zero* nudges/halts on the cooperative shared `DEMO_PROMPTS` - that's
the correct, honest result, not a failed demo - with a separate, clearly-
labeled non-deterministic stress-prompt cell for anyone who wants to
actually try to trip it live.

Verified: `uv run pytest` (90 passed, up from 67), `ruff check` clean on
every new/changed file, notebook JSON structurally valid (50 cells, every
code cell parses). Manually smoke-tested both optimizations end-to-end
through a real `AgentLoop` with a scripted fake LLM client (no network) -
confirmed loop-guard's sent/sent/nudged/nudged/halted progression skips the
real call on halt, and context-window's pruning + `load_skill` both work
through the actual tool loop with the dedup fix in place. Also confirmed
`loop-guard` + `context-window` compose cleanly, and `context-window` +
`conversation-summary` correctly raises `ConflictingOptimizationsError`
(both own `history_policy`). Did **not** run the notebook against a real
API key (would cost real money) - that's still owed if you want to confirm
the live-model prose reads well, not just that the code path works.

### [2026-08-13] Notebook: re-applied Opt 2/3 restructure after pull --rebase

User did `git pull --rebase` from main; the rebase pulled a newer upstream
notebook (now 52 cells, adds Opt 4 Agent loop prevention + Opt 5 Context window)
and dropped our earlier edits: order was back to Opt 2 = Model routing, Opt 3 =
Cache-friendly, no tier table, no 2a/2b split. Re-applied our changes on top of
the new upstream version.

Changes (notebook only):
- Swapped so the flow matches the deck: **Opt 2 = Prompt optimization & caching**
  (2a Prompt optimization [conceptual - trim + cache prefix, groundwork], 2b
  Cache-friendly prompts [live, with layer-by-volatility table]) -> **Opt 3 =
  Model routing** (added the 3-tier table). Physically moved the cache block
  above routing; kept the routing code cells (opt_routing, /metrics,
  routing_report) in place and only rebuilt the intro.
- Tier table uses the CURRENT models.yaml ladder pulled in by the rebase:
  low `google/gemma-3.4b` 0.05/0.10, mid `qwen/qwen3.7-flash` 0.03/0.13, high
  `deepseek/deepseek-v4-flash-0731` 0.08/0.252 (note: this main uses gemma, not
  the mistral-nemo from the other branch's models.yaml - kept it consistent with
  what's actually committed here).
- Left Opt 4 (loop prevention) and Opt 5 (context window) untouched - we never
  edited those. NOTE for user: the deck orders context-window (50) BEFORE
  loop-prevention (60), but the notebook has loop-prevention as Opt 4 and
  context-window as Opt 5; flagged, not changed (out of scope of our edits).

Verified: valid JSON, 52 cells, 24 code cells, 0 parse errors, section flow
1 summary -> 2 caching(2a/2b) -> 3 routing -> 4 loop -> 5 context -> stack.

### [2026-08-13] Two observability tiers: lightweight in-memory + real OpenTelemetry

Added monitoring as its own concern, split into two independently
`--enable`-able tiers rather than one optimization, after working through
what each is actually FOR: teaching the concept fast (zero setup, for
100% of a live workshop room) vs. genuine hands-on exposure to real OTel
tooling (worth real setup friction, but as an explicitly optional/advanced
path, not something the whole room does live on the clock).

**`observability`** (lightweight): mirrors every other optimization's "own
tracker, own command, own per-turn line" shape. Needed a hook none of
`OptimizationBundle`'s four fields provided - none of them see individual
*tool* execution, only `wrap_llm_client` sees model calls - so added a 5th,
symmetric hook: `wrap_tool_registry` (`Callable[[ToolExecutor], ToolExecutor]`,
composes via the same `_compose` helper). `ToolExecutor` is a new `Protocol`
in `tools/registry.py` (`definitions()` + `execute()`) - the same
dependency-inversion move `LLMClient` already made for `wrap_llm_client`.
`optimizations/observability.py`'s `ObservabilityTracker` records latency +
success/failure for every LLM/tool call via two decorators that never
swallow an error (record, then re-raise/return exactly what the inner call
would have); `/observability` reports call counts, error rate, latency, a
per-tool breakdown, and the most recent failures by name and message.

**`observability-otel`** (advanced, separate optimization, composes with
the above): real OpenTelemetry traces/metrics/logs exported to an actual
Grafana. New deps: `opentelemetry-api`/`sdk`/`exporter-otlp-proto-http`
(HTTP/protobuf, not gRPC - pure-Python, no `grpcio` native wheel, matters
for the Windows/ARM-Mac workshop audience). Reuses the same
`wrap_llm_client`/`wrap_tool_registry` hooks, but each call becomes a real
span (`llm.call`/`tool.call`, marked error + a bridged stdlib-`logging`
log record on failure) plus counter/histogram metrics via
`_instruments()`. `build()` reads `Config.otel_exporter_otlp_endpoint`/
`_headers` and fails fast (`MissingOtelEndpointError`) if unset - same "no
silent defaults" rule as everywhere else - rather than silently exporting
nowhere.

Getting an endpoint took a long design detour before any code got
written: a *shared* hosted backend (one Grafana for every attendee) was
considered and explicitly rejected mid-design - concurrency, cross-attendee
visibility, and hosting/ops burden. Confirmed via research (not assumed)
that the workshop notebook runs on Colab's *hosted* runtime (`# /content
on Colab`, `google.colab` secrets), which has zero network/filesystem
access to an attendee's own machine - a hard platform boundary, so a
purely local backend only works if Colab is first connected to a [local
runtime](https://research.google.com/colaboratory/local-runtimes.html)
(itself real setup: Jupyter + the Colab extension + Docker already
installed - confirmed Colab's own docs, not stale memory). Landed on: every
attendee gets their own fully isolated backend, no shared infra at all -
**local** (`optimizations/observability_stack.py`'s
`start_local_observability_stack()`, one Docker image `grafana/otel-lgtm`
bundling a pre-wired Collector + Tempo + Prometheus + Loki + Grafana,
idempotent start/reuse, OS-aware guidance when Docker's missing/not
running) or **cloud** (attendee's own free Grafana Cloud stack - confirmed
current free-tier limits via research: 50GB traces/logs, 10k metric
series/mo, 14-day retention, no card - pastes the `OTEL_EXPORTER_OTLP_*`
values its own "Configure" button generates). Both converge on the exact
same two `Config` fields, so the instrumentation code never needs to know
which one it's talking to.

Notebook: rebased these two new sections onto the *latest* upstream
notebook (52 cells, the Opt 2/3 caching-before-routing restructure landed
in a separate "Refactor notebook" + "Update docs" commit pair after this
branch forked) rather than the version this branch started from - located
the insertion point by content (the cell whose source is exactly
`opt_context["session"].context_report()`), not a hardcoded index, so it
landed correctly right after context-window/before "Stack them" in the
new ordering. "Optimization 6 - Observability" (lightweight, same
markdown-intro -> `run_scenario` -> `compare` -> `/x_report()` pattern as
every other section, plus a deterministic "debugging becomes easier" demo -
ask it to read a file that provably doesn't exist, print `/usage` next to
`/observability` on the same session to contrast "1 tool call happened"
against "`read_file` failed on `does_not_exist_xyz.py` after 0ms") and
"Optimization 7 - Advanced observability" (explicitly marked optional/
skippable, local-path cell + cloud-path `EDIT ME` cell mirroring Step 3's
style, conditional on an endpoint actually being set). Added to the "Stack
them" `compare()` call and the final scoreboard `runs` list (lightweight
tier only - the advanced tier's tokens/cost are identical to baseline by
design, and its setup is conditional/optional, so it doesn't belong in an
unconditional scoreboard row).

Verified: `uv run pytest` (120 passed, up from 90), `ruff check` clean on
every new/changed file, notebook JSON structurally valid (64 cells now,
every code cell parses). Real end-to-end smoke tests, not just unit tests -
Docker Engine is actually available in this environment (confirmed via
`docker info`), so this got tested against a genuinely live stack: spun up
a real `grafana/otel-lgtm` container, sent real spans/metrics through the
actual OTLP/HTTP exporters, and confirmed `force_flush()` succeeded over
the real network (not just that construction didn't throw). Confirmed a
real failing tool call is recorded correctly by the lightweight tier
through the actual `WorkshopSession`/`AgentLoop` machinery (no mocking of
the tool registry itself). Confirmed `observability` +
`observability-otel` + `hybrid-routing` all compose through the real CLI
startup path with no `ConflictingOptimizationsError` (none of the three
own `history_policy`). This dev machine happened to already be running an
unrelated observability stack (`numad-*` containers) on the same default
ports (4317/3000) - worked around by testing on alternate ports rather
than touching those containers; the shipped code's defaults are unaffected.
Did **not** verify the cloud path (Grafana Cloud) - no test account
available in this environment - and did not run the notebook against a
real model (no API key here) - both still owed, same caveat as every
prior notebook change.

## [2026-08-13] Prompt optimization as the five-technique family (3 new optimizations)

Reframed "prompt optimization" across repo -> notebook -> deck as a family
of five techniques - context pruning, conversation summarization, tool
filtering, prompt compression, deduplication - and implemented the three
that didn't exist, so all five are now live behind their own flags.
Caching content stays in 2b (cache-friendly prompts); 2a is now purely
the token-reduction family.

New optimizations (all `wrap_llm_client` decorators, so they compose with
everything - no `history_policy` conflicts):
- `tool-filtering` (optimizations/tool_filtering.py): withholds the
  action tools (write_file/edit_file/bash) from sends whose latest user
  message shows no matching intent, via word-boundary keyword heuristics
  (free, local - same stance as routing's difficulty scorer). Safety
  rules, in priority order: exploration tools (read_file/list_files) and
  unknown/extra tools (e.g. load_skill) are never withheld; a tool
  already used this turn's loop stays exposed; no confident match ->
  all tools kept. /toolfilter + `_format_tool_filter_summary`.
- `prompt-compression` (optimizations/prompt_compression.py): swaps in
  hand-tightened SYSTEM_PROMPT_COMPACT (new, in system_prompt.py, 925 ->
  480 chars) + compact tool descriptions at the send boundary.
  Deliberately deterministic - a human tightened the text once, reviewed
  for equal meaning; never an LLM rewriting at runtime (tokens to save
  tokens, silent meaning drift). Substring-replaces exactly SYSTEM_PROMPT
  inside the outgoing system string so suffixes appended by other
  optimizations (context-window's skills menu) pass through; unknown
  tools keep their original descriptions. /compression + per-turn line.
- `deduplication` (optimizations/deduplication.py): keeps the first
  occurrence of any text block >= AGENT_DEDUP_MIN_CHARS (new required
  env knob, default 200 in .env.example) and replaces later *exact*
  duplicates (tool results, repeated pasted instructions) with a marker
  naming what it duplicates and its size. Exact string match only, no
  similarity; no message ever removed, tool_use/tool_result pairing and
  is_error flags untouched; AgentLoop's own history untouched (send-
  boundary copy only). /dedup + per-turn line.

Notebook: 2a rewritten as the five-technique taxonomy table (each flag +
where measured, cross-refs to Opt 1/Opt 5 as the two history-policy
members); new "anatomy of a request" cell prints the REAL system prompt
(both variants), a real tool definition, and a sample conversation run
through the repo's own PromptBuilder - stable/semi-stable/dynamic layers
in real bytes with the stable-prefix hash (verified against the real
API: 88% stable share on the sample). Three new scenario+report cells
(same run_scenario/compare pattern); caching prose (cache-hit ~10%
billing, volatility table) consolidated into 2b's markdown; DEMO_PROMPTS
gained a 6th verification turn ("Read calculator.py and
test_calculator.py again...") so dedup has an honest, natural trigger
(re-reading unchanged files) and tool filtering a read-only turn -
same fixed set for every scenario, so comparisons stay fair. Stack cell
now runs six flags; scoreboard includes the three new runs.

Deck: slide 30 stays hybrid per request - new pc-family sub-slide (five
cards + flags, blue = history-policy members, turmeric = wrappers),
pc-sep split pills (optimization live / caching in progress), pc-plan
cards updated, pc-concept kicker now "Prompt caching"; intro + closing
status rows for "Prompt optimization & caching" flipped to live.

AGENTS.md: new "Prompt optimization (the five-technique family)" section,
module map + per-turn-summary list extended. Config: dedup_min_chars
(fail-fast _require_int, same as every knob); notebook config cell
setdefaults it; the three existing build()-test env helpers gained the
new var.

Verified: uv run pytest 147 passed (was 120; +27 across
test_tool_filtering/test_prompt_compression/test_deduplication - fakes
only, no HTTP); real CLI startup with all four
prompt-optimization-adjacent flags combined (prompt-compression,
deduplication,tool-filtering,cache-friendly-prompts) - no conflict; one
real OpenRouter turn through the wrappers (per-turn compression line +
/compression agree: system 925->480, tool docs 791->455 chars); anatomy
cell logic exercised against the real PromptBuilder. Local .env gained
the four knobs it was missing (predates loop-guard/context-window) plus
AGENT_DEDUP_MIN_CHARS. Not verified: full notebook run against a live
model end-to-end (baseline + 9 scenarios costs real money), and the
benchmark with the new flags - both owed, same caveat as prior notebook
changes.

[2026-08-14] Notebook: made Colab Secrets the ONLY source for the API key - removed the API_KEY="..." paste field and the getpass hidden-prompt fallback; _load_api_key() now reads userdata only and raises a clear "add it in the Secrets panel" error if missing. Also removed the OTEL cloud-path paste fields (OTEL_ENDPOINT/OTEL_HEADERS) - both read from Colab secrets instead. Root-cause note: upstream commit dfcdcd5 (remove monitoring) deleted the whole observability-otel section, so that notebook edit is moot now - only the Step 3 API-key change survived the rebase.
[2026-08-14] Commit 976c6c4 (pushed): notebook Colab-secrets change + restored report.py flush=True prints (they had been wiped by a second fast-forward pull; restored from backup and committed). Also had to stash/rebase around dfcdcd5 which rewrote 559 lines of the same notebook - resolved by resetting notebook to upstream then re-applying the Step 3 change.

[2026-08-14] Notebook: rewrote all 33 markdown cells to concise bullet instructions - removed prose/explanation, kept all tables (model presets, five techniques, request anatomy, cache layers, routing tiers) and terminal commands. ~25K -> ~11.6K markdown chars.

[2026-08-14] Notebook: collapsed all 31 code cells (metadata "collapsed": true) so the notebook opens collapsed from GitHub. Replaced Step 3 EDIT-ME constants and the free-play cell with input() terminal prompts (provider, model, task, optimizations). API key still read only from Colab Secrets - never prompted. nbformat-validated.

[2026-08-14] Notebook: merged ALL setup cells (title intro, clone, install, config, sanity check, measurement harness, run_scenario) into ONE collapsed code cell + one minimal title markdown. First visible section is now "Meet the base agent". Setup flow: run the single setup cell -> it prompts for provider/model, reads Colab secret, installs, pings. 53 cells total, all code collapsed.

[2026-08-14] Notebook: added key registration flow - title cell now points users to https://key-distribution.vercel.app/w/G04eDpFeZl3DfKBy5uHtYA to register their email and get an OpenRouter key. Setup cell now asks (in order): provider -> model -> paste API key (input prompt showing the register link). Colab secret is still read automatically first if present, else the paste prompt appears.

[2026-08-14] Notebook: simplified setup - removed provider/model prompts entirely. Provider fixed to openrouter, model fixed to deepseek/deepseek-v4-flash-0731. Setup cell now asks for ONLY the OpenRouter API key (Colab secret read automatically first, else paste prompt with register link).

---

## Session: consolidated spikes notes into 2 topics

User restructured the talk into TWO topics (was three): (1) Prompt Optimization &
Caching, (2) Model Routing. Re-checked the repo — working-tree changes were
cosmetic only (`presentation/js/hud.js` delta-persist tweak; `.gitignore` now
ignores `spikes/` and `playground/`); slide `.js` content unchanged, so the
earlier analysis of the implementation still holds.

Replaced the three per-slide-range files with two:
- `spikes/slides-12-18-prompt-optimization-and-caching.md` — merges the old
  12–14 (caching idea) + 15–18 (cache-friendly construction) into one narrative:
  problem → two levers (trim + cache) → the byte-identical-prefix prerequisite →
  live impl (builder memoization, serializer determinism, provider_adapter seam,
  /cache metrics) → hands-on. Notes it's part-live (cache-friendly) /
  part-in-progress (provider cache directive).
- `spikes/slides-19-22-model-routing.md` — routing notes, retitled "Model
  Routing", content carried over (features/router/tiers/quality_gate/
  hybrid_routing/metrics, the vocab-independent-signals bug fix, data-driven
  ladder). Deleted the old `slides-12-14.md`, `slides-15-18.md`, `slides-19-22.md`.

Note: `spikes/` is now gitignored, so these notes live locally and won't be
committed.

---

## Session: added the prompt-optimization FAMILY to the spikes notes

User flagged the spikes MD didn't cover deduplication / the other prompt-
optimization techniques now in the deck. Re-analysed:
- `presentation/slides/30-prompt-caching.js` was expanded (3 -> 5 slides) into a
  "prompt optimization is a FAMILY" section, and the working tree had just edited
  it from FIVE cards to FOUR (deduplication card removed; context pruning,
  conversation summarization, tool filtering, prompt compression remain).
- The code, however, has ALL of them live in `optimizations/available.py`:
  context-window, conversation-summary, tool-filtering, prompt-compression,
  deduplication (+ loop-guard, observability, observability-otel).
- Deck slide numbers shifted: Prompt Optimization & Caching = slides 12-20,
  Model Routing = slides 21-24.

Actions:
- Replaced `slides-12-18-*.md` with `slides-12-20-prompt-optimization-and-caching.md`,
  adding a full PART A "family" section: one subsection per technique (waste
  removed / how it works / safety / code file / flag / /command), the
  history-owner vs wrap-the-call (blue vs turmeric) grouping, and the
  ConflictingOptimizationsError one-history-owner rule. Kept PART B caching.
  Read each impl to keep it accurate: context_window.py (ContextPruningPolicy +
  skills), conversation_summary.py (running cached summary, counted in /usage),
  tool_filtering.py (action-tools-only, keep-on-uncertainty), prompt_compression.py
  (hand-tightened, not a runtime model), deduplication.py (exact-match marker).
- Noted deck currently shows four cards (dedup pulled) but kept dedup notes so the
  presenter can speak to it / re-add it; it's `--enable deduplication`.
- Renamed routing file to `slides-21-24-model-routing.md` and fixed its internal
  slide-number refs (ladder 20->22, callout 21->23, notebook 22->24).
[2026-08-14] Notebook: "Meet the base agent" smoke test simplified - no hardcoded model override, uses default deepseek model; demo prompt shortened to just "hi".

[2026-08-14] Notebook: updated key registration link to the real prod URL (key-distribution.vercel.app/w/wAwE5_U3QvomPo1YIgSHJg) in the title cell and the setup cell KEY_URL.

[2026-08-14] Notebook: "Meet the base agent" demo prompt restored to "Create hello.py that prints Hello workshop, then show me its contents." (was briefly shortened to "hi").

[2026-08-14] Presentation: added a QR code (colab-notebook-qr.png) on the TITLE slide pointing to the Colab notebook link, positioned bottom-right, styled via .qr-wrap in layouts.css. Verified it decodes correctly with jsQR and renders without overlapping the headline.
