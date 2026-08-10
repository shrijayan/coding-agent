# AGENTS.md

Instructions for any human or AI agent working in this repository.

## What this is

A minimal coding agent (like Claude Code/OpenCode) built from scratch to
understand how these tools work under the hood. It's a terminal chat loop
backed by an LLM (Claude directly, or any model via OpenRouter), with a
small set of tools (read/write/edit files, run bash, list files) that let
the model actually act on this machine instead of just talking about it.

This project doubles as the **Base Agent for a workshop on agent cost/
performance optimization**. The idea: everyone builds their own
optimization (conversation summarization, caching, model routing,
context window optimization, ...) on top of this same base, using its
built-in token/cost tracking (`/usage`, see below) to prove - not just
claim - that their optimization actually helps. See "How to add a new
optimization" below for the exact pattern every optimization plugs into.

## Quick start

```bash
uv sync                        # install dependencies into .venv
cp .env.example .env           # set AGENT_PROVIDER + that provider's API key
uv run coding-agent            # start the chat loop
```

Type `exit` (or Ctrl+D / Ctrl+C) to quit.

There are no automated tests yet (v1 was validated manually end-to-end).
If you add tests, run them with `uv run pytest`.

## How the agent loop actually works

1. User types a message -> `AgentLoop.run_turn()`.
2. The loop sends the full conversation history + system prompt + tool
   schemas to the model via `LLMClient.send()`.
3. The model replies with either final text, or a request to call one or
   more tools (`LLMResponse.wants_tool_use`).
4. If tools were requested, `ToolRegistry.execute()` runs each one for
   real and the result goes back into the conversation as a tool result.
5. Repeat from step 2 until the model replies with plain text (no more
   tool calls) - that text is the final answer shown to the user.

`AgentLoop` (src/coding_agent/agent/loop.py) is the file that ties this
together. Read that first if you want to understand the whole system.

## Module map

```
src/coding_agent/
├── __init__.py           # exposes main() - the package's only entry point
├── cli.py                 # REPL: reads input, wires everything together, prints output
├── cli_args.py             # parses --enable and --benchmark flags
├── config.py               # loads + validates config: models.yaml defaults + env (fail-fast)
├── models.yaml              # SINGLE SOURCE OF TRUTH for models: default provider/model,
│                            #   per-model price + metadata catalog, routing ladder, cost cap
├── models_config.py         # loads/validates models.yaml (used by config, pricing, tiers)
├── system_prompt.py         # the agent's system prompt text
├── agent/
│   ├── conversation.py     # message history, in our own provider-agnostic format
│   ├── loop.py             # AgentLoop - the orchestrator described above
│   └── factory.py           # build_agent() - assembles an AgentLoop from Config + optimizations
├── llm/
│   ├── base.py             # LLMClient interface + LLMResponse/LLMError (provider-agnostic)
│   ├── messages.py         # Message/TextPart/ToolUsePart/ToolResultPart - the neutral conversation format
│   ├── factory.py          # picks which LLMClient to build, based on Config.provider
│   ├── anthropic_client.py # concrete LLMClient that calls the Anthropic Messages API
│   └── openrouter_client.py # concrete LLMClient that calls OpenRouter (OpenAI-compatible API)
├── metrics/
│   ├── usage.py             # Usage (token counts) + UsageTracker (accumulates across a session)
│   ├── pricing.py            # PricingTable - cost = tokens x models.yaml catalog, fail-fast if unpriced
│   └── cost_guard.py          # CostGuard - soft per-session spend cap (protects a shared budget)
├── commands/
│   ├── base.py              # SlashCommand interface (mirrors tools/base.py's Tool)
│   ├── registry.py           # SlashCommandRegistry - looks up and runs commands by name
│   └── usage_command.py       # /usage - prints tokens, cost, call counts for the session
├── optimizations/
│   ├── bundle.py             # OptimizationBundle - what one optimization changes, + merge logic
│   ├── registry.py            # OptimizationRegistry - resolves --enable names into a bundle
│   ├── available.py            # AVAILABLE_OPTIMIZATIONS - the one registration point (cli.py + benchmark share it)
│   └── history_policy.py        # HistoryPolicy interface + DefaultHistoryPolicy (send everything)
├── benchmark/
│   ├── tasks.py              # 3 hand-verified SWE-bench Lite tasks (BenchmarkTask + TASKS)
│   ├── data/<instance_id>/    # each task's problem statement, test patch, FAIL_TO_PASS/PASS_TO_PASS
│   ├── sandbox.py             # Docker-free repo checkout + pinned venv + test patch application
│   ├── runner.py               # runs one task through a fresh AgentLoop, checks pass/fail
│   └── report.py                # runs every task, prints per-task + aggregate summary
└── tools/
    ├── base.py             # Tool interface + ToolResult
    ├── registry.py          # ToolRegistry - looks up and runs tools by name
    ├── read_file.py
    ├── write_file.py
    ├── edit_file.py
    ├── bash.py
    └── list_files.py
```

## Conventions (please follow these when changing code)

- **Fail fast on configuration, recover gracefully on runtime errors.**
  Missing/invalid env vars raise `MissingConfigError` immediately at
  startup (see `config.py`) - never add a silent fallback default.
  A tool failing at runtime (file not found, bad command, ...) must
  **not** crash the program - catch it and return `ToolResult.error(...)`
  so the model sees the error as text and can adjust, the same way a
  human developer reacts to a failed command. The same applies to the
  LLM call itself: `LLMClient` implementations translate their
  provider's exceptions into `LLMError` (see `llm/base.py`), which the
  CLI catches, shows as one clean `error>` line, and keeps the session
  running - a bad key or a rate limit shouldn't kill the whole program
  any more than a missing file should.
- **No hardcoded config values.** Anything that could reasonably change
  per environment (model name, token limits, timeouts, iteration caps)
  lives in `.env` / `Config`, injected into constructors - never a bare
  constant buried in a tool or client file.
- **Dependency injection everywhere.** `AgentLoop`, `ToolRegistry`,
  every `LLMClient` implementation, and every `Tool` receive their
  dependencies through `__init__`, not by constructing them internally.
  This is what makes it possible to swap the LLM provider or test with
  fake tools without touching the loop.
- **One file, one responsibility.** Each tool is its own file. If a file
  starts doing two unrelated things, split it.
- **Conversation history is provider-agnostic.** `Conversation` stores
  `llm/messages.py` types (`Message`, `TextPart`, `ToolUsePart`,
  `ToolResultPart`), never a specific provider's wire format. Each
  `LLMClient` translates neutral <-> its own wire format right at the
  API boundary (see `_to_anthropic_messages` / `_to_openai_messages`).
  If you add a provider whose wire format doesn't fit this neutral
  shape, extend `llm/messages.py` deliberately - don't leak a
  provider-specific dict shape back out into `Conversation` or `AgentLoop`.
- **Never estimate tokens or cost.** `Usage` is only ever populated from
  a provider's real API response (see `llm/base.py`'s `LLMResponse.usage`
  docstring). Every optimization built on this base gets judged by
  `/usage` numbers - a guessed token count would make every comparison
  in the workshop meaningless, so this is a hard rule, not a style
  preference.
- **Slash commands mirror tools.** `SlashCommand`/`SlashCommandRegistry`
  (`commands/`) are the exact same "registry of named, pluggable things"
  shape as `Tool`/`ToolRegistry` (`tools/`), applied to REPL-level
  commands like `/usage` instead of model-invoked actions. If a new kind
  of pluggable thing needs to be added later (e.g. an optimization
  registry), reach for this same shape rather than inventing a new one.

## How to add a new tool

This is the most common change you'll make. Steps:

1. Create `src/coding_agent/tools/your_tool.py` with a class extending
   `Tool` (see `tools/base.py`). Implement `name`, `description`,
   `input_schema`, and `run()`.
   - `run()` must never raise for expected failures - return
     `ToolResult.ok(...)` or `ToolResult.error(...)`.
   - Write `description` for the model, not for a human reader - it's
     part of the prompt and directly affects whether Claude uses the
     tool correctly.
2. Register it in `agent/factory.py`'s `build_agent()`, in the `tools=[...]` list.
3. If the tool needs any configurable value (a timeout, a size limit,
   ...), add it to `.env.example` and `Config` first, then pass it into
   your tool's constructor - don't hardcode it.
4. Test it manually by running `uv run coding-agent` and asking Claude to
   use it.

## Adding a new LLM provider

There are two today (`anthropic`, `openrouter`) - both follow this same
recipe, so a third is additive, not a rewrite:

1. Create `src/coding_agent/llm/your_provider_client.py` with a class
   implementing `LLMClient` (`llm/base.py`). Its `send()` must:
   - Translate the incoming `list[Message]` (neutral, `llm/messages.py`)
     into that provider's own wire format - see `_to_anthropic_messages`
     or `_to_openai_messages` for the pattern. Pay attention to how tool
     calls/results are represented; every provider does this differently
     (Anthropic folds them into content blocks, OpenAI-style APIs use a
     separate `tool_calls` field and a `role="tool"` message).
   - Translate that provider's own tool-definition shape from our neutral
     `{name, description, input_schema}` (already just JSON schema).
   - Catch that provider's SDK exceptions around the actual API call and
     re-raise as `LLMError` with a short, human-readable reason - check
     what the SDK's `.body`/`.message` actually contain by triggering a
     real error first, don't assume it matches another provider's SDK
     (the `anthropic` and `openai` SDKs looked identical on the surface
     but shaped their error `.body` differently - verified, not assumed).
   - Parse the response back into `LLMResponse(text, tool_calls,
     wants_tool_use, usage)`. `usage` must come from the provider's real
     response (e.g. Anthropic's `response.usage.input_tokens`, OpenAI-
     style APIs' `response.usage.prompt_tokens`) - never estimated, since
     every cost comparison in this project depends on it being real.
2. Add the provider to `_PROVIDER_API_KEY_ENV_VARS` in `config.py` and
   `_BUILDERS` in `llm/factory.py`.
3. Add its API key variable and an example model string to `.env.example`.
4. Test manually: run with a deliberately invalid key first (confirms
   the whole plumbing reaches the real API and errors come back clean),
   then with a real key and a prompt that exercises every tool.

## Model config (models.yaml)

`src/coding_agent/models.yaml` is the single source of truth for **which**
models the agent uses. It's plain data (loaded via `models_config.py`), so
swapping a model, re-pricing one, reordering the routing ladder, or editing
the cost cap is a one-line edit with no code change. Secrets never live
here - API keys stay in `.env`. Four sections:

- `default:` - the base agent's provider/model/max_tokens when routing is
  off. `AGENT_PROVIDER`/`AGENT_MODEL`/`AGENT_MAX_TOKENS` in `.env` override
  these per-person, so nobody has to edit the shared file to point at their
  own model.
- `session_cost_cap_usd:` - the soft per-session spend cap (see below).
- `models:` - the catalog: `input_per_million_usd`/`output_per_million_usd`
  **and** `metadata` (description, context_window, strengths,
  good_for_difficulty) for every model named anywhere in the file. Every
  model used (base default AND every routing tier) MUST have an entry or the
  agent refuses to start. Metadata is stored context for `/usage` and for a
  future capability-aware router - it is NOT yet consumed by routing (which
  still decides on `difficulty_ceiling`).
- `routing:` - the hybrid-routing ladder (cheapest first) plus
  `quality_gate_enabled` / `ollama_base_url`. Each tier names a `model` from
  the catalog; its provider is resolved from that catalog entry (or set
  `provider: inner` to reuse AGENT_MODEL).

## Token/cost tracking

`metrics/usage.py`'s `UsageTracker` records real token counts (never
estimated - see `LLMResponse.usage`'s docstring) after every model call,
*attributed per model* (`by_model`), and `metrics/pricing.py`'s
`PricingTable` turns those into a dollar estimate using the `models.yaml`
catalog. If a model you use has no catalog entry, the agent refuses to
start (`MissingPricingError`) rather than silently showing `$0.00` - add
an entry under `models:` with `input_per_million_usd`/
`output_per_million_usd` for the exact model string.

**Session cost cap.** `metrics/cost_guard.py`'s `CostGuard` enforces
`session_cost_cap_usd`: before each model call, if the session's estimated
cost has crossed the cap, `AgentLoop` stops and returns a notice instead of
spending more. It's a *soft* cap (checked before each call, so a session
overshoots by at most one in-flight call) whose purpose is protecting a
shared, fixed budget across many participants. The interactive REPL enforces
it (cli.py passes `pricing` into `build_agent`); the benchmark deliberately
does not (a controlled measurement shouldn't be cut off mid-task). Override
per-person with `AGENT_SESSION_COST_CAP_USD` (a number, or `none`).

Type `/usage` in any session to see the running total for that session:
turns, LLM calls, tool calls, tokens, cost, and which optimizations are
currently enabled. This is the tool every optimization gets judged
with - see the next section.
Besides `/usage`, every turn also prints a one-line **per-turn summary**
right after the agent's answer (see `cli.py`). What's on it depends on
the mode in use, and each mode shows only the data that actually applies
to it:

- base agent (no flags): `↳ <model> · <n> LLM calls · <tokens> tokens ·
  <wall-clock>ms · $<cost>` (`_format_turn_summary`)
- `--enable hybrid-routing`: the routing line instead - path, tier/model,
  difficulty score, quality-gate outcome, model latency, cost
  (`_format_routing_summary`) - because difficulty and gate results only
  exist when routing is active.

If you build an optimization that introduces its own mode with its own
extra signals (the way hybrid-routing has difficulty/gate data), give it
its own per-turn line in `cli.py` showing only the fields relevant to
that mode - don't leave the user with no per-turn feedback, and don't
pad a generic line with fields that are meaningless in your mode.
## How to add a new optimization

This project is the shared **Base Agent** for a workshop where several
people each build one optimization (conversation summarization, caching,
model routing, context window optimization, prompt optimization, output
style control, inference parameters, ...) on top of it. Every
optimization plugs in the same way, through `OptimizationBundle`
(`optimizations/bundle.py`), regardless of who builds it or what it
does - so this section should be enough on its own to build and wire up
a new one.

### Step 1: figure out which hook(s) you need

An `OptimizationBundle` has three fields. Set only the one(s) relevant
to what your optimization actually changes - most optimizations need
exactly one:

| Field | Set this if your optimization... | Examples |
|---|---|---|
| `history_policy` | changes what conversation history is sent to the model | conversation summarization, context window optimization |
| `wrap_llm_client` | changes something about the model call itself | caching, model routing, inference parameters (top_p/top_k) |
| `system_prompt_suffix` | is really just an instruction to the model | prompt optimization, output length/style control |

### Step 2: implement it

Create `src/coding_agent/optimizations/your_optimization.py`. Pick the
pattern(s) that match Step 1:

**If you set `history_policy`** - implement `HistoryPolicy`
(`optimizations/history_policy.py`):

```python
from coding_agent.llm.messages import Message
from coding_agent.optimizations.history_policy import HistoryPolicy

class YourPolicy(HistoryPolicy):
    def prepare(self, messages: list[Message]) -> list[Message]:
        # Return what should actually be sent to the model this turn.
        # AgentLoop's own record of the conversation is untouched no
        # matter what you return here - only what gets sent is affected.
        ...
```

**If you set `wrap_llm_client`** - `LLMClient` (`llm/base.py`) is
already an interface, so wrapping it needs no new abstraction, just the
Decorator pattern: a class that implements `LLMClient` and holds
another `LLMClient` inside it:

```python
from coding_agent.llm.base import LLMClient, LLMResponse
from coding_agent.llm.messages import Message

class YourWrapper(LLMClient):
    def __init__(self, inner: LLMClient) -> None:
        self._inner = inner

    def send(self, *, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        # Do something before/instead of/after calling the real client:
        return self._inner.send(system=system, messages=messages, tools=tools)
```

**If you set `system_prompt_suffix`** - just write the instruction text
as a string; no class needed.

Then add a small factory function in the same file:

```python
from coding_agent.optimizations.bundle import OptimizationBundle

def build() -> OptimizationBundle:
    return OptimizationBundle(history_policy=YourPolicy())  # or wrap_llm_client=..., etc.
```

If your optimization needs its own settings (a threshold, a cache TTL,
...), add them to `.env.example` and `Config` first, then read them in
`build()` - don't hardcode them, same rule as everywhere else in this
project.

### Step 3: register it

One line in `optimizations/available.py`'s `AVAILABLE_OPTIMIZATIONS` dict:

```python
AVAILABLE_OPTIMIZATIONS: dict[str, Callable[[], OptimizationBundle]] = {
    "your-optimization-name": your_optimization.build,
}
```

That's the only place that needs to change - `AgentLoop`, `cli.py`, and
the benchmark runner all already work with whatever bundle comes out of
the registry, unchanged.

### Step 4: prove it, don't just claim it

1. `uv run coding-agent --enable your-optimization-name` and confirm
   the agent still behaves correctly on a few real prompts.
2. Run the *same* prompt with and without your flag, and compare
   `/usage` output between the two runs - turns, tokens, and cost. That
   before/after comparison is the actual deliverable for the workshop,
   not just working code.
3. For a more rigorous check that also catches correctness regressions
   (not just cost), run the benchmark suite with and without your flag
   - see "Benchmark" below.

### Combining optimizations

`--enable a,b` (or `--enable a --enable b`) combines both bundles
automatically (`OptimizationBundle.merged_with`): `wrap_llm_client`
wrappers chain (both take effect, first-enabled applied outermost),
`system_prompt_suffix` values concatenate. `history_policy` has only
one owner at a time - if two enabled optimizations both set one,
`ConflictingOptimizationsError` is raised rather than one silently
winning. If your optimization and someone else's both need to control
history, that's a real design conversation to have, not something to
resolve by picking whichever runs last.

## Benchmark

`uv run coding-agent --benchmark` (optionally combined with `--enable`)
runs a fixed suite of real coding tasks and prints a report: how many
resolved, total tokens, total cost, wall-clock time. This is the
rigorous counterpart to eyeballing `/usage` before/after - it checks
that an optimization didn't quietly break correctness while saving
tokens, using a task the model can't "cheat" on the way it might on an
arbitrary prompt (see the next paragraph for why the task has to be fixed).

**The tasks never change, on purpose.** Each is a real GitHub issue from
[SWE-bench Lite](https://www.swebench.com) with a real hidden test that
only passes once the issue is genuinely fixed (`benchmark/tasks.py`,
data in `benchmark/data/<instance_id>/`). The prompt is always this same
fixed `problem_statement`, never whatever a user types interactively -
if the task varied between runs, a token/cost difference could just
mean the task changed, not that an optimization helped. Holding the
task constant and varying only the optimization is what makes "40% fewer
tokens with X enabled" a comparison you can trust.

**No Docker.** Unlike the official SWE-bench harness (~120GB disk,
16GB+ RAM, ~60 environment images - see
[Docker Setup](https://www.swebench.com/SWE-bench/guides/docker_setup/)),
`benchmark/sandbox.py` clones each task's repo into a plain `uv`-managed
virtual environment with the exact Python version and pinned
dependencies that instance needs. This trades some environment fidelity
for a fast, live-workshop-friendly loop.

**Only 3 tasks are curated** (of SWE-bench Lite's 534), each
individually verified end-to-end before being added - the environment
installs cleanly, the FAIL_TO_PASS tests genuinely fail before a fix and
genuinely pass after the real one - rather than a general "run any
instance" loader. If you want to add a 4th: pick a lightweight repo
(pure Python, no C-extension build - flask/requests/pytest/pylint style,
not sklearn/matplotlib/astropy), verify it the same manual way first
(clone, checkout, install, apply test patch, confirm fail-then-pass),
*then* add it to `TASKS` - don't add an instance you haven't personally
watched go from failing to passing.

**Two non-obvious things this runner had to handle**, in case you're
debugging a task that won't resolve even though the fix looks right -
see `benchmark/runner.py`'s docstrings for the full reasoning:
- The raw GitHub issue text is often phrased as a question, not an
  instruction - passed to the agent unwrapped, it will just answer
  conversationally instead of editing code. `runner.py` wraps it in an
  explicit "resolve this issue by editing the code" framing.
- Hitting `AGENT_MAX_ITERATIONS` doesn't mean the task failed - the
  agent's edits already happened on disk regardless of whether it
  converged to a final answer, so the runner always checks the tests
  afterward rather than assuming failure. (Confirmed necessary in
  practice, not theoretical: a run hit the iteration limit while
  re-verifying an already-correct fix, and was still correctly counted
  as resolved.)


## Logging changes

Every session of work on this repo should end with an entry appended to
`devxdocs/agentlog.md` (append only - don't read the whole file unless
you need historical context, and don't rewrite past entries).
