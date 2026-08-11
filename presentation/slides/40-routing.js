/* ==================================================== 40 · MODEL SELECTION & ROUTING
   Technique #3 - LIVE in the repo. Showcase animation: the routing LADDER.
   A request is scored for difficulty and starts at the cheapest tier that
   covers it; a quality gate can escalate one rung. The ladder demo keeps
   its fragments + HUD; the "how" slide is a static visual.
============================================================================ */

Deck.add({
  id: "route-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:var(--tw-jade);">
      <div class="bar"></div>
      <div class="idx">Technique 03</div>
      <h1>Model selection &amp; routing</h1>
      <p>Don't send every request to your best (most expensive) model. Match the model to the difficulty of the ask.</p>
      <div class="sep-meta">
        <span class="pill live"><span class="dot"></span>live in the repo</span>
        <div class="flag">--enable hybrid-routing</div>
      </div>
    </div>
  `,
  notes: `Presenter Two. The base agent sends everything to one model. Routing sends easy work to a cheap model and reserves the strong one for genuinely hard requests.`,
});

Deck.add({
  id: "route-ladder",
  hud: true,
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
          <div class="mdl">small &amp; fast model<br/>~$0.1 per M tokens</div>
          <div><span class="runmark">${TW.icon('check')} runs</span><span class="failmark">gate &#10007;</span></div>
        </div>
        <div class="rung mid">
          <div><div class="tier">mid</div><div class="tag">&le; 0.75</div></div>
          <div class="mdl">balanced model<br/>~$0.5 per M tokens</div>
          <div><span class="runmark">${TW.icon('check')} runs</span></div>
        </div>
        <div class="rung high">
          <div><div class="tier">high</div><div class="tag">&le; 1.0</div></div>
          <div class="mdl">strongest model<br/>~$2 per M tokens</div>
          <div><span class="runmark">${TW.icon('check')} runs</span></div>
        </div>
      </div>
    </div>

    <div class="stepline" style="margin-top:12px;font-size:0.9em;color:var(--tw-ink-soft);">
      <span class="fragment current-visible" data-fragment-index="0"
            data-set-state="1" data-state-el="#ladder" data-tokens="2600" data-cost="0.0303"
            data-hint="easy -> cheapest model">
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
        <b>Hard</b> scores 0.92 &rarr; goes straight to <b>high</b>. No wasted cheap attempt.
      </span>
      <span class="fragment current-visible" data-fragment-index="3"
            data-set-state="4" data-state-el="#ladder" data-tokens="2600" data-cost="0.0356"
            data-hint="cascade: gate failed -> escalate once">
        <b>Cascade:</b> cheap answered but failed the quality gate &rarr; escalate one rung, retry.
      </span>
    </div>
  `,
  notes: `The showcase for routing. Two paradigms working together:
  PRE-routing (the gauge) - score difficulty 0-1 locally (free) and start at the cheapest tier whose ceiling covers it, so hard requests skip cheap entirely.
  CASCADE (state 4) - a deterministic quality gate checks the output; on failure it escalates ONE rung and retries.
  Watch the meter: most requests are easy, so cost creeps instead of leaping. Contrast with "everything on the strongest model".`,
});

Deck.add({
  id: "route-how",
  html: `
    <div class="slide-head">
      <div class="kicker">03 &middot; How it decides</div>
      <h2>The ladder is data, not code</h2>
    </div>
    <div class="icon-rows" style="margin-top:20px;">
      <div class="icon-row jade"><div class="ic">${TW.icon('gauge')}</div><div class="tx"><b>Score locally, for free.</b> Difficulty is estimated without any model call &mdash; then the request starts at the first tier that covers it.</div></div>
      <div class="icon-row turmeric"><div class="ic">${TW.icon('shield')}</div><div class="tx"><b>Quality gate.</b> A deterministic check on the answer; on failure, escalate one rung and retry until it passes.</div></div>
      <div class="icon-row wave"><div class="ic">${TW.icon('route')}</div><div class="tx"><b>Tiers live in a config file.</b> Add a tier or swap a model by editing one line &mdash; no code changes.</div></div>
    </div>
    <div class="callout" style="margin-top:22px;">
      Routing decides on <b>every model call</b> &mdash; many times per turn, not once per question.
    </div>
  `,
  notes: `Presenter Two. Hybrid beats either alone: pure pre-routing wastes the strong model on requests that only LOOKED hard; pure cascading always pays for a cheap attempt first even on obviously-hard ones. Scoring then gating spends the expensive model only when actually needed. The ladder is pure data in models.yaml.`,
});

Deck.add({
  id: "route-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Route a mixed workload</h2>
      <p class="lead" style="max-width:44ch;">Give the agent a mix of trivial and hard asks, and watch which tier each request lands on.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Optimization 3 &mdash; Model routing&rdquo;</div>
          <div class="s">Run the mixed task set, then check the per-tier breakdown and total cost.</div>
        </div>
        <div class="nb-cmd">--enable hybrid-routing</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">Compare total cost against the same workload on the strong tier alone &mdash; that gap is the routing win.</p>
    </div>
  `,
  notes: `Hands on. Everyone runs the mixed workload with routing on. Look at /metrics: how many requests hit cheap vs high, and the total vs an all-strong-model baseline.`,
});
