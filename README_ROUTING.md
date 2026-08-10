# Hybrid Routing: cheapest model that answers well enough

`--enable hybrid-routing` adds a cost-optimizing layer to the terminal
agent. It is one `OptimizationBundle` (see `AGENTS.md`), so it turns on
with a flag and needs no other wiring:

```bash
uv run coding-agent --enable hybrid-routing
uv run coding-agent --benchmark --enable hybrid-routing   # measure it
```

## Why

Most requests a coding assistant gets are easy ("reverse a string",
"rename this variable"). Sending every one of them to a large, paid model
is like taking a taxi to your mailbox. The idea — straight from the
"Dynamic Model Routing and Cascading for Efficient LLM Inference" survey —
is to always use **the cheapest model that still answers well enough**,
and only pay for the expensive one when it's actually needed.

This implementation combines **two** of the survey's six paradigms, which
is why it beats either one on its own:

1. **Difficulty-aware pre-generation routing.** Before spending a single
   token, each request is scored 0.0–1.0 for difficulty using *free,
   local* signals (length, code fences, keyword hits — no model call, no
   network). Clearly hard requests skip the cheap tier entirely.
2. **Post-generation cascade.** Easy-scored requests go to a **local,
   free** model (Ollama) first. A deterministic **quality gate** then
   checks that output, and only if it fails do we **escalate** to the
   powerful paid model.

Pure pre-routing alone wastes the expensive model on requests that merely
*looked* hard. Pure cascading alone always pays for a throwaway cheap
generation first, even on obviously-hard requests. Scoring first and
gating second spends the expensive model only when it's genuinely needed.

## Architecture

```
User types a prompt into the running terminal REPL
  │
  ▼
Feature extraction (routing/features.py)
  - vocabulary-INDEPENDENT: length, long-word density, clause complexity
  - vocabulary-dependent:   easy/hard keyword hits, code fences
  │                                    (free, local, no model call)
  ▼
Router (routing/router.py) — weighted sum → difficulty_score (0-1)
  │
  ▼
Pick the starting rung: the first tier whose difficulty_ceiling >= score
  (models.yaml routing.tiers, ordered cheapest → strongest)
  │
  ├─ scored 0.20 → start at "cheap"     (skips nothing)
  ├─ scored 0.60 → start at "mid"       (skips cheap)
  └─ scored 0.95 → start at "strong"    (skips cheap AND mid)
  │
  ▼
That tier answers
  │
  ▼
Quality gate (routing/quality_gate.py) — deterministic, free
  - ast_valid / unterminated_code_fence / empty_response
  - refusal / placeholder_code / missing_tool_arguments
  │
  ├── PASS ─────────────────────────────────────────────► Use this answer
  └── FAIL ──► climb ONE rung and retry ──┐
                 ▲                        │
                 └────────────────────────┘  (until PASS, or ladder exhausted;
                                              the top rung's answer is kept
                                              even if it fails — nothing better exists)
  │
  ▼
Record one RoutingRecord (path, tier, hops, difficulty, real tokens, gate result)
  │
  ▼
CLI prints a compact routing annotation for the turn; /metrics shows the session total
```

**One important subtlety:** the routing decision happens per
`LLMClient.send()`, which is **not** once per user turn. The agent runs a
tool-use loop — one thing you type can trigger many `send()` calls (one
per tool round-trip). So each `send()` is scored and routed
individually, and the terminal prints a compact *per-turn* summary of
those records rather than spamming one line per internal call.

## Configuring the model ladder

**Which models are in the ladder, how many there are, and their order all
live in one data file** — `src/coding_agent/models.yaml`, under the
`routing:` section (the same file holds the model catalog and prices).
Adding a middle tier is a data edit, not a code change:

```yaml
routing:
  quality_gate_enabled: true
  ollama_base_url: http://localhost:11434/v1
  tiers:
    - name: cheap
      model: deepseek/deepseek-v4-flash-0731
      difficulty_ceiling: 0.45
    - name: mid
      model: thinkingmachines/inkling-small
      difficulty_ceiling: 0.75
    - name: high
      model: qwen/qwen3.8-max
      difficulty_ceiling: 1.0
```

- **Order matters**: cheapest/weakest first, strongest last.
- **`difficulty_ceiling`** is the hardest request that tier is trusted
  with. It drives the pre-generation routing decision, and must increase
  down the list. The last tier must be `1.0` (it's the catch-all).
- **`model`** names an entry from the `models:` catalog in the same file;
  its **provider is resolved from that catalog entry**. To reuse whatever
  `AGENT_PROVIDER`/`AGENT_MODEL` is configured, set `provider: inner` on
  the tier (with no `model`), so there's no duplicate copy of your main
  model setting to keep in sync.
- Every model named here **already has its price + metadata** in the
  `models:` catalog (local models at `0.0`/`0.0`). The agent checks all of
  them at startup and refuses to start otherwise, rather than silently
  reporting `$0.00`.
- A tier whose API key isn't set is **skipped at startup with a warning**,
  so a partially-configured ladder still runs.

Validation is fail-fast: a ladder with descending ceilings, a duplicate
name, a missing model, or a last tier that isn't `1.0` raises
`InvalidTierConfigError` at startup instead of misrouting silently.

### Adding a provider that doesn't exist yet

Three small edits (the repo is designed for this): implement `LLMClient`
in `llm/your_client.py`, add one entry to `_API_KEY_BUILDERS` in
`llm/factory.py`, and one to `_PROVIDER_API_KEY_ENV_VARS` in `config.py`.
Then you can name it in `models.yaml`.


## How difficulty is scored (and why it isn't just a keyword list)

The scorer is a weighted sum of signals in two deliberate groups:

**Vocabulary-independent** (these generalize to words nobody listed):
- **length** — longer requests trend harder
- **long-word density** — fraction of words ≥ 9 characters, a proxy for
  technical register (`backpressure`, `idempotent`, `serialization`) that
  needs no keyword list
- **clause complexity** — sentences plus connectives, i.e. how many
  separate things are being asked at once

**Vocabulary-dependent** (a precision boost, not the foundation):
- hard/easy keyword hits, code fences

> **Why the split matters.** The first version of this scorer leaned
> entirely on keyword lists, and had a structural bug: with zero keyword
> hits the maximum achievable score was **0.50**, below the 0.55
> threshold — so a genuinely hard request phrased in unlisted vocabulary
> could **never** reach a strong tier, no matter how hard it was. The
> vocabulary-independent signals now sum to **0.70** on their own, above
> any sane threshold. Both properties are locked in by regression tests
> (`test_scorer_detects_hard_request_using_no_known_keywords` uses a hard
> prompt containing zero listed keywords).

**Honest limitation:** the pre-router is a cheap *prior*, not an oracle.
A short but conceptually hard request (~20 words, no listed keywords) can
still score below the threshold and start on a cheap tier. That's by
design — catching it is the quality gate's job, which is why the gate
matters at least as much as the router.

## The quality gate

Every check is deterministic, runs in microseconds, and needs no model
call. Each is concrete evidence that a tier got it wrong:

| Check | Catches |
|---|---|
| `ast_valid=false` | a ```python block that doesn't parse |
| `unterminated_code_fence` | output truncated mid-code-block |
| `empty_response` | no text, no code, no tool calls |
| `refusal` | "I can't help with that" / "I don't know" |
| `placeholder_code` | `# TODO: implement` stubs instead of real code |
| `missing_tool_arguments` | a tool call omitting a required parameter |

Checks are deliberately **conservative** — a false FAIL costs a real
escalation to a paid model. A hedging phrase like "I'm not sure this is
idiomatic" is ignored when the model *also* produced code or called a
tool, since the work actually got done.

`ruff`/`pytest` are intentionally **not** run here: at the `send()`
boundary the response is usually tool calls plus prose, not a standalone
file. Those only make sense on files already written to disk later in the
tool loop, so they're left as an optional extension.

## Terminal UX

After each answer, a plain-text annotation shows which tier handled it:

```
you> write a function that reverses a string
agent> [response from cheap tier]
  ↳ cheap · cheap/qwen2.5-coder:7b · difficulty 0.00 · quality gate PASS · 640ms · $0.0000

you> design a multi-tenant rate limiter backed by Redis with failure-mode trade-offs
agent> [response from the strong tier, which the pre-router picked directly]
  ↳ direct_powerful · powerful/claude-sonnet-5 · difficulty 0.63 · 2100ms · $0.0041

you> [a prompt where the cheap tier emitted broken code]
agent> [response from the next tier up, after the cheap output failed the gate]
  ↳ cheap_escalated · ast_valid=false → escalated +1 tier · powerful/claude-sonnet-5 · difficulty 0.20 · 1900ms · $0.0038
```

A turn that spans several internal `send()`s (the tool loop) collapses to
a compact roll-up — this one is **real output** from a live run where a
local model handled an entire tool-using turn for free:

```
  ↳ routing: 3 sends · 3 cheap · 19566ms · $0.0000
```

Type **`/metrics`** any time for the session aggregate — path breakdown,
which tier actually answered, escalation rate, quality-gate pass rate,
latency by path, and cost (derived from real token counts × the
`models.yaml` catalog, never estimated — the same rule `/usage` follows):

```
--- Routing metrics (this session) ---
Total routed calls : 7
  direct_powerful  : 2
  cheap            : 4
  cheap_escalated  : 1
Escalation rate    : 20.0% (of cheap-tier attempts)
Quality-gate pass  : 85.7%
Answered by tier:
  cheap            : 4
  mid              : 1
  strong           : 2
Avg latency by path:
  direct_powerful  : 2050ms
  cheap            : 660ms
  cheap_escalated  : 1900ms
Total routed cost  : $0.0082
Avg cost per call  : $0.0012
```

Two metrics that answer different questions:
- **Escalation rate** — how often a tier's output wasn't good enough,
  as a fraction of attempts that *could* have escalated.
- **Quality-gate pass** — of all sends where the gate ran, how often the
  tier the pre-router *chose* produced acceptable output. This measures
  the routing decision, not just the cheap model.

## Running it locally

1. **Install and start Ollama**, then pull the cheap-tier model:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
   (Ollama serves an OpenAI-compatible API at `http://localhost:11434/v1`,
   which is how the cheap tier plugs into the same `LLMClient` abstraction
   as every other provider — no extra dependency.)

2. **Configure `.env`** (copy from `.env.example`) with your API keys. The
   base model, the routing ladder, prices, and per-model metadata all live
   in `src/coding_agent/models.yaml`; a tier with `provider: inner` reuses
   `AGENT_PROVIDER` / `AGENT_MODEL` / `<PROVIDER>_API_KEY`. The two
   routing-specific settings default from `models.yaml`'s `routing:` block
   and can be overridden in `.env`:
   ```
   AGENT_ROUTING_OLLAMA_BASE_URL=http://localhost:11434/v1
   AGENT_ROUTING_QUALITY_GATE_ENABLED=true
   ```
   The models themselves live in `models.yaml` (see "Configuring the model
   ladder" above), not in `.env`.

3. **Launch as usual, with the flag:**
   ```bash
   uv run coding-agent --enable hybrid-routing
   ```

### Graceful fallbacks (a demo never hard-fails)

- **A tier is unreachable** (Ollama not running, model not pulled) → that
  rung surfaces a clean error and the request falls through to the next
  rung up, recorded with reason `tier_error`. Only if the *top* rung
  fails does the error reach you. Fix it by starting `ollama serve` and
  pulling the model.
- **A tier's API key isn't set** → that tier is skipped at startup with a
  `warning>` line and the ladder runs on the remaining rungs. So a
  cheap-only ladder still fully demonstrates feature extraction, routing,
  the gate, and `/metrics` before any paid key lands; once it's set,
  escalation works with zero code changes.
- **The top rung's answer fails the gate** → it's kept anyway. There's
  nothing better to escalate to, and returning the best available answer
  beats returning nothing.
- **A model in `models.yaml`'s ladder has no catalog price entry** →
  startup fails fast with an actionable message, rather than silently
  reporting `$0.00`.

### Testing the escalation path before a licensed key arrives

To exercise the full cheap→gate→escalate→powerful path end-to-end before a
licensed powerful-model key is issued, you can temporarily point the
powerful tier at one of OpenRouter's rate-limited free model slugs
(suffixed `:free` — check OpenRouter's current model list, it changes) by
setting `AGENT_PROVIDER=openrouter`, `AGENT_MODEL=<some>/<model>:free`, and
a free `OPENROUTER_API_KEY`, plus a matching `models.yaml` catalog entry.
Swap to the licensed model string once issued — no other code changes
needed. That's exactly how the routing/escalation/metrics plumbing was
validated here before the licensed model landed.

## How to extend (the survey's upgrade path)

The heuristic scorer in `routing/router.py` is intentionally simple and
readable. Once `/metrics` (or a persisted `routing_logs`) has real data
mapping **features → did-it-escalate**, that heuristic can be replaced by a
trained `scikit-learn` classifier (the survey's "supervised classifier" /
"bandit" upgrade) with **zero changes to its callers**: `router.py`
already exposes the exact drop-in seam —

```python
def predict(features: Features) -> float:
    ...  # today: the readable heuristic; tomorrow: a loaded model's probability
```

Two further opt-in upgrades are deliberately left as hooks, not built now:

- **Embedding features.** `routing/features.py` uses lexical signals so
  `--enable hybrid-routing` works out of the box with no heavy install.
  A MiniLM embedding + cosine similarity to easy/hard exemplar sets can
  be added as an opt-in feature source (pulls in `sentence-transformers`
  + `torch`, hence opt-in). This is the principled fix for the "short but
  conceptually hard request" limitation noted above.
- **Cost/latency as routing inputs.** Today cost is *measured and
  reported*, but it does not influence the routing decision — difficulty
  and the gate do. A budget-aware policy ("stay under $X/session",
  "prefer the cheapest tier meeting a latency SLO") would read the same
  `RoutingTracker` data `/metrics` already collects.
- **Persisted routing logs.** Metrics are in-memory per session, matching
  `UsageTracker`. Persisting them (SQLite or JSONL) is what would supply
  the training data for the classifier above.

### What's already configurable (no code change)

- **Number of tiers, their order, models, and providers** →
  `models.yaml` (`routing:` + `models:`)
- **Where each tier's cutoff sits** → `difficulty_ceiling` per tier
- **Prices + per-model metadata used for cost reporting** →
  `models.yaml` (`models:` catalog)
- **The per-session spend cap** → `models.yaml` `session_cost_cap_usd`
  (or `AGENT_SESSION_COST_CAP_USD`)
- **Whether the gate runs** → `AGENT_ROUTING_QUALITY_GATE_ENABLED`
  (or `models.yaml` `routing.quality_gate_enabled`)
- **Which model the `inner` tier uses** → `AGENT_PROVIDER` / `AGENT_MODEL`
  (or `models.yaml` `default:`)

### A note on Terraform

Terraform provisions *infrastructure* (cloud resources, with state and a
plan/apply lifecycle). This routing layer is runtime configuration for a
local terminal process — there's nothing to provision. `models.yaml` is
the right shape for it: plain, checked-in data, the same way model prices
and defaults already live in this repo. If you later host the agent
somewhere, Terraform would manage that hosting, not this ladder.

