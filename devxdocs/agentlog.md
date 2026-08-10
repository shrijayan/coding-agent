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
