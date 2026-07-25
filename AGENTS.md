# AGENTS.md

Instructions for any human or AI agent working in this repository.

## What this is

A minimal coding agent (like Claude Code/OpenCode) built from scratch to
understand how these tools work under the hood. It's a terminal chat loop
backed by Claude, with a small set of tools (read/write/edit files, run
bash, list files) that let the model actually act on this machine instead
of just talking about it.

## Quick start

```bash
uv sync                        # install dependencies into .venv
cp .env.example .env           # then fill in ANTHROPIC_API_KEY at minimum
uv run coding-agent            # start the chat loop
```

Type `exit` (or Ctrl+D / Ctrl+C) to quit.

There are no automated tests yet (v1 was validated manually end-to-end).
If you add tests, run them with `uv run pytest`.

## How the agent loop actually works

1. User types a message -> `AgentLoop.run_turn()`.
2. The loop sends the full conversation history + system prompt + tool
   schemas to Claude via `LLMClient.send()`.
3. Claude replies with either final text, or a request to call one or
   more tools (`stop_reason == "tool_use"`).
4. If tools were requested, `ToolRegistry.execute()` runs each one for
   real and the result goes back into the conversation as a `tool_result`
   message.
5. Repeat from step 2 until Claude replies with plain text (no more tool
   calls) - that text is the final answer shown to the user.

`AgentLoop` (src/coding_agent/agent/loop.py) is the file that ties this
together. Read that first if you want to understand the whole system.

## Module map

```
src/coding_agent/
├── __init__.py           # exposes main() - the package's only entry point
├── cli.py                 # REPL: reads input, wires everything together, prints output
├── config.py               # loads + validates env vars (fail-fast, no hidden defaults)
├── system_prompt.py         # the agent's system prompt text
├── agent/
│   ├── conversation.py     # message history, in the Anthropic wire format
│   └── loop.py             # AgentLoop - the orchestrator described above
├── llm/
│   ├── base.py             # LLMClient interface + LLMResponse/ToolCall/LLMError (provider-agnostic)
│   └── anthropic_client.py # concrete LLMClient that calls the Anthropic Messages API
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
  `AnthropicClient`, and every `Tool` receive their dependencies through
  `__init__`, not by constructing them internally. This is what makes it
  possible to swap the LLM provider or test with fake tools without
  touching the loop.
- **One file, one responsibility.** Each tool is its own file. If a file
  starts doing two unrelated things, split it.

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
2. Register it in `cli.py`'s `_build_agent()`, in the `tools=[...]` list.
3. If the tool needs any configurable value (a timeout, a size limit,
   ...), add it to `.env.example` and `Config` first, then pass it into
   your tool's constructor - don't hardcode it.
4. Test it manually by running `uv run coding-agent` and asking Claude to
   use it.

## Adding a second LLM provider (if/when needed)

Create a new class implementing `LLMClient` (src/coding_agent/llm/base.py)
next to `anthropic_client.py`, returning `LLMResponse` the same way. Wire
the choice of client in `cli.py`. Don't build this speculatively before
it's actually needed - YAGNI.

## Logging changes

Every session of work on this repo should end with an entry appended to
`devxdocs/agentlog.md` (append only - don't read the whole file unless
you need historical context, and don't rewrite past entries).
