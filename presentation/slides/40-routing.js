/* ==================================================== 40 · MODEL SELECTION & ROUTING
   Technique #3 - LIVE in the repo (--enable hybrid-routing).
   Showcase animation: the routing LADDER. A request is scored 0-1 for
   difficulty and starts at the cheapest tier that covers it; a quality gate
   can escalate one rung. Grounded in optimizations/hybrid_routing.py + models.yaml.
============================================================================ */

Deck.add({
  id: "route-sep",
  hideHud: true,
  html: `
    <div class="separator">
      <div class="txt">
        <div class="idx">Technique 03</div>
        <h1>Model selection<br/>&amp; routing</h1>
        <p>Don't send every request to your best (most expensive) model. Match the model to the difficulty of the ask.</p>
        <div style="margin-top:18px;"><span class="pill live"><span class="dot"></span>live in the repo</span></div>
      </div>
      <div class="visual grad">
        <div style="text-align:center;color:#fff;">
          <div style="font-size:3em;">${TW.icon('route')}</div>
          <div style="font-family:var(--tw-mono);font-size:0.72em;margin-top:12px;opacity:0.9;">--enable hybrid-routing</div>
        </div>
      </div>
    </div>
  `,
  notes: `Presenter Two. The base agent sends everything to one model. Routing sends easy work to a cheap model and reserves the strong one for genuinely hard requests.`,
});

Deck.add({
  id: "route-ladder",
  hideHud: false,
  tokens: 2600,
  cost: 0.0300,
  html: `
    <div class="slide-head">
      <div class="kicker">03 &middot; Model selection &amp; routing</div>
      <h2>Score first, escalate only if needed</h2>
    </div>

    <div class="ladder" id="ladder" data-state-initial="1">
      <div class="meter">
        <div class="gauge"><div class="inner">
          <div class="val">
            <span class="state-item s-1">0.31</span>
            <span class="state-item s-2">0.68</span>
            <span class="state-item s-3">0.92</span>
            <span class="state-item s-4">0.38</span>
          </div>
          <div class="cap">difficulty</div>
        </div></div>
        <div class="req">
          <div class="state-item s-1">&ldquo;<b>rename</b> a variable across a file&rdquo;</div>
          <div class="state-item s-2">&ldquo;<b>debug</b> this failing test&rdquo;</div>
          <div class="state-item s-3">&ldquo;design a <b>concurrency-safe</b> queue&rdquo;</div>
          <div class="state-item s-4">&ldquo;easy-looking, but the cheap answer <b>failed the gate</b>&rdquo;</div>
        </div>
      </div>

      <div class="rungs">
        <div class="rung cheap">
          <div><div class="tier">cheap</div><div class="tag">&le; 0.45</div></div>
          <div class="mdl">deepseek-v4-flash<br/>$0.09 / $0.18 per M</div>
          <div><span class="runmark">${TW.icon('check')} runs</span><span class="failmark">gate &#10007;</span></div>
        </div>
        <div class="rung mid">
          <div><div class="tier">mid</div><div class="tag">&le; 0.75</div></div>
          <div class="mdl">inkling-small<br/>$0.45 / $1.20 per M</div>
          <div><span class="runmark">${TW.icon('check')} runs</span></div>
        </div>
        <div class="rung high">
          <div><div class="tier">high</div><div class="tag">&le; 1.0</div></div>
          <div class="mdl">qwen3.8-max<br/>$2.00 / $6.00 per M</div>
          <div><span class="runmark">${TW.icon('check')} runs</span></div>
        </div>
      </div>
    </div>

    <div class="stepline" style="margin-top:12px;font-size:0.84em;color:var(--tw-ink-soft);">
      <span class="fragment current-visible" data-fragment-index="0"
            data-set-state="1" data-state-el="#ladder" data-tokens="2600" data-cost="0.0303"
            data-hint="easy -> cheapest model, ~$0.0003">
        <b>Easy</b> request scores 0.31 &rarr; starts at <b>cheap</b>. Cost barely moves.
      </span>
      <span class="fragment current-visible" data-fragment-index="1"
            data-set-state="2" data-state-el="#ladder" data-tokens="2600" data-cost="0.0312"
            data-hint="medium -> mid tier, cheap skipped">
        <b>Medium</b> scores 0.68 &rarr; skips cheap, starts at <b>mid</b>.
      </span>
      <span class="fragment current-visible" data-fragment-index="2"
            data-set-state="3" data-state-el="#ladder" data-tokens="2600" data-cost="0.0342"
            data-hint="hard -> strong model directly">
        <b>Hard</b> scores 0.92 &rarr; goes straight to <b>high</b>. No wasted cheap attempt first.
      </span>
      <span class="fragment current-visible" data-fragment-index="3"
            data-set-state="4" data-state-el="#ladder" data-tokens="2600" data-cost="0.0356"
            data-hint="cascade: gate failed -> escalate once">
        <b>Cascade:</b> cheap answered but failed the quality gate &rarr; escalate one rung to <b>mid</b>, retry.
      </span>
    </div>
  `,
  notes: `The showcase for routing. Two paradigms working together:
  PRE-routing (the gauge) - score difficulty 0-1 locally (free) and start at the cheapest tier whose ceiling covers it, so hard requests skip cheap entirely.
  CASCADE (state 4) - a deterministic quality gate checks the output; on failure it escalates ONE rung and retries.
  Watch the meter: most requests are easy, so cost creeps instead of leaping. Contrast with "everything on qwen3.8-max at $2/$6 per M".`,
});

Deck.add({
  id: "route-how",
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">optimizations/hybrid_routing.py &middot; models.yaml</div>
      <h2>The ladder is data, not code</h2>
    </div>
    <div class="split top" style="grid-template-columns:0.95fr 1.05fr;">
      <div class="col">
        <div class="code-panel">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="fn">models.yaml &middot; routing.tiers</span></div>
          <pre><code class="language-yaml" data-trim>routing:
  quality_gate_enabled: true
  tiers:
    - name: cheap
      model: deepseek/deepseek-v4-flash-0731
      difficulty_ceiling: 0.45
    - name: mid
      model: thinkingmachines/inkling-small
      difficulty_ceiling: 0.75
    - name: high
      model: qwen/qwen3.8-max
      difficulty_ceiling: 1.0</code></pre>
        </div>
      </div>
      <div class="col">
        <div class="icon-rows">
          <div class="icon-row green"><div class="ic">${TW.icon('gauge')}</div><div class="tx"><b>Pre-route.</b> Score 0&ndash;1 locally &mdash; free, no model call &mdash; then start at the first tier that covers it.</div></div>
          <div class="icon-row amber"><div class="ic">${TW.icon('shield')}</div><div class="tx"><b>Quality gate.</b> A deterministic check on the output; escalate one rung on failure until it passes or the ladder ends.</div></div>
          <div class="icon-row teal"><div class="ic">${TW.icon('route')}</div><div class="tx"><b>N tiers, data-driven.</b> Add a tier or swap a model in <code>models.yaml</code> &mdash; the wrapper never counts them.</div></div>
        </div>
        <div class="callout" style="margin-top:12px;">Decides per <code>LLMClient.send()</code> &mdash; many times per turn, not once. The CLI prints a per-turn routing summary.</div>
      </div>
    </div>
  `,
  notes: `Presenter Two. Hybrid beats either alone: pure pre-routing wastes the strong model on requests that only LOOKED hard; pure cascading always pays for a cheap attempt first even on obviously-hard ones. Scoring then gating spends the expensive model only when actually needed. The ladder length/models are pure data in models.yaml.`,
});

Deck.add({
  id: "route-notebook",
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Route a mixed workload</h2>
    </div>
    <p class="lead" style="max-width:42ch;">Give the agent a mix of trivial and hard asks, and watch which tier each request lands on.</p>
    <div class="notebook-cue">
      <div class="nb-ic">Jupyter</div>
      <div class="nb-tx">
        <div class="t">Notebook &rarr; &ldquo;Optimization 2 &mdash; Model routing&rdquo;</div>
        <div class="s">Run the mixed task set, then check <code>/metrics</code> for the per-tier breakdown and total cost.</div>
      </div>
      <div class="nb-cmd">uv run coding-agent --enable hybrid-routing</div>
    </div>
    <p class="muted" style="font-size:0.8em;margin-top:16px;">Compare total cost against the same workload on the strong tier alone &mdash; that gap is the routing win.</p>
  `,
  notes: `Hands on. Everyone runs the mixed workload with routing on. Look at /metrics: how many requests hit cheap vs high, and the total vs an all-strong-model baseline.`,
});
