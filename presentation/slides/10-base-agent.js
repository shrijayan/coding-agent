/* ===================================================== 10 · BASE CODING AGENT
   What the repo actually is, the agent loop, its tools/providers, and the
   built-in token/cost tracking - which is where the HUD makes its entrance.
   Grounded in the real repo: agent/loop.py, tools/, llm/, metrics/, /usage.
============================================================================ */

Deck.add({
  id: "base-intro",
  hideHud: true,
  html: `
    <div class="separator">
      <div class="txt">
        <div class="idx">Our starting point</div>
        <h1>A tiny coding agent, built from scratch</h1>
        <p>A terminal chat loop backed by an LLM, with real tools that let the model act on your machine &mdash; not just talk about it. Everything today is an optimization <em>on top of this</em>.</p>
      </div>
      <div class="visual grad">
        <div style="color:#fff;text-align:center;font-family:var(--tw-mono);font-size:0.8em;line-height:1.9;">
          <div style="font-family:var(--tw-serif);font-size:1.7em;font-weight:800;margin-bottom:10px;">~1,500 LOC</div>
          read &middot; write &middot; edit<br/>bash &middot; list_files<br/>Anthropic &middot; OpenRouter
        </div>
      </div>
    </div>
  `,
  notes: `This is the shared "Base Agent". Small on purpose - you can read the whole thing. The point of the workshop: everyone layers one optimization onto this same base and proves it helps with real numbers.`,
});

Deck.add({
  id: "agent-loop",
  hideHud: true,
  html: `
    <div class="slide-head">
      <div class="kicker">agent/loop.py</div>
      <h2>The whole system is one loop</h2>
    </div>
    <div style="display:flex;flex-direction:column;gap:16px;height:calc(100% - 96px);justify-content:center;">
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;align-items:stretch;">
        <div class="fragment rise loopnode" data-fragment-index="0" style="background:var(--tw-card);border-radius:10px;padding:14px;text-align:center;">
          <div style="font-size:1.6em;color:var(--tw-coral);">${TW.icon('agent')}</div>
          <div style="font-weight:700;font-size:0.74em;margin-top:6px;">1 &middot; You ask</div>
          <div style="font-size:0.62em;color:var(--tw-muted);margin-top:2px;">a message enters the loop</div>
        </div>
        <div class="fragment rise" data-fragment-index="1" style="background:var(--tw-teal-900);color:#fff;border-radius:10px;padding:14px;text-align:center;">
          <div style="font-size:1.6em;">${TW.icon('bolt')}</div>
          <div style="font-weight:700;font-size:0.74em;margin-top:6px;">2 &middot; LLM.send()</div>
          <div style="font-size:0.62em;color:#bcd3d9;margin-top:2px;">history + system + tools</div>
        </div>
        <div class="fragment rise" data-fragment-index="2" style="background:var(--tw-card);border-radius:10px;padding:14px;text-align:center;">
          <div style="font-size:1.6em;color:var(--tw-amber);">${TW.icon('route')}</div>
          <div style="font-weight:700;font-size:0.74em;margin-top:6px;">3 &middot; Text or tools?</div>
          <div style="font-size:0.62em;color:var(--tw-muted);margin-top:2px;">wants_tool_use</div>
        </div>
        <div class="fragment rise" data-fragment-index="3" style="background:var(--tw-card);border-radius:10px;padding:14px;text-align:center;">
          <div style="font-size:1.6em;color:var(--tw-green);">${TW.icon('check')}</div>
          <div style="font-weight:700;font-size:0.74em;margin-top:6px;">4 &middot; Run tools</div>
          <div style="font-size:0.62em;color:var(--tw-muted);margin-top:2px;">ToolRegistry.execute()</div>
        </div>
        <div class="fragment rise" data-fragment-index="4" style="background:var(--tw-card);border-radius:10px;padding:14px;text-align:center;">
          <div style="font-size:1.6em;color:var(--tw-coral);">${TW.icon('loop')}</div>
          <div style="font-weight:700;font-size:0.74em;margin-top:6px;">5 &middot; Feed back</div>
          <div style="font-size:0.62em;color:var(--tw-muted);margin-top:2px;">result &rarr; step 2</div>
        </div>
      </div>
      <div class="fragment fade-in callout" data-fragment-index="5">
        Loop until the model replies with <b>plain text and no tool calls</b> &mdash; that's the answer. Every trip through step&nbsp;2 is a <b>real API call</b>, so every trip costs tokens. <b>That's what we optimize.</b>
      </div>
    </div>
  `,
  notes: `Walk the five steps. Emphasise: the tool loop makes MANY model calls per user turn, not one. So "cost per turn" is really "sum of every send() in that turn" - important later for routing.`,
});

Deck.add({
  id: "cost-tracking",
  hideHud: false,
  tokens: 1850,
  cost: 0.0,
  html: `
    <div class="slide-head">
      <div class="kicker">metrics/usage.py &middot; metrics/pricing.py</div>
      <h2>It counts every real token &amp; dollar</h2>
    </div>
    <div class="split top" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <p class="lead">Token counts come only from the provider's real response &mdash; <em>never estimated</em>. Cost = tokens &times; the price catalog in <code>models.yaml</code>.</p>
        <div class="stack-sm" style="margin-top:10px;">
          <div class="fragment fade-in" data-fragment-index="0" data-tokens="1850" data-cost="0.0000">
            <span class="pill planned"><span class="dot"></span>fresh session</span> &nbsp; the meter starts at zero &rarr;
          </div>
          <div class="fragment fade-in" data-fragment-index="1" data-tokens="6300" data-cost="0.0058" data-hint="one turn = several tool-loop calls">
            <b>Turn 1</b> &mdash; a few tool-loop calls. Watch the meter move.
          </div>
          <div class="fragment fade-in" data-fragment-index="2" data-tokens="11200" data-cost="0.0121" data-hint="history keeps growing every turn">
            <b>Turn 2</b> &mdash; history grows, so the next call is bigger&hellip; and pricier.
          </div>
        </div>
        <div class="fragment fade-in callout" data-fragment-index="3" style="margin-top:14px;">
          Type <code>/usage</code> anytime for the session total. <b>This</b> is how every optimization gets judged &mdash; before vs after, no hand-waving.
        </div>
      </div>
      <div class="col">
        <div class="visual-panel" style="align-items:flex-start;">
          <div class="kicker" style="margin-bottom:12px;">Meet the meter &#8599;</div>
          <p style="font-size:0.86em;color:var(--tw-ink-soft);">Top-right, all session long:</p>
          <ul style="font-size:0.82em;color:var(--tw-ink-soft);">
            <li><b>Context tokens</b> &mdash; how big the next call is.</li>
            <li><b>Session cost</b> &mdash; cumulative $ spent, only ever goes up.</li>
          </ul>
          <p style="font-size:0.78em;color:var(--tw-muted);margin-top:8px;">Good optimizations pull tokens <b>down</b> while barely moving cost <b>up</b>. You'll watch that trade-off happen live.</p>
        </div>
      </div>
    </div>
  `,
  notes: `THE HUD APPEARS NOW. Advance the fragments slowly so the room notices the numbers tween. Key line: tokens are never estimated - only real provider counts. The whole workshop is trustworthy because of this.`,
});

Deck.add({
  id: "base-notebook",
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Let's run the base agent together</h2>
    </div>
    <p class="lead" style="max-width:40ch;">Open the notebook you were given and run the first section: a plain agent, no optimizations. Note the baseline <code>/usage</code>.</p>
    <div class="notebook-cue">
      <div class="nb-ic">Jupyter</div>
      <div class="nb-tx">
        <div class="t">Notebook &rarr; &ldquo;Baseline &mdash; the un-optimized agent&rdquo;</div>
        <div class="s">Run the cells, give it a small task, then read the token &amp; cost total.</div>
      </div>
      <div class="nb-cmd">uv run coding-agent</div>
    </div>
    <p class="muted" style="font-size:0.8em;margin-top:16px;">We'll come back here after each technique. Keep your baseline number &mdash; every optimization is measured against it.</p>
  `,
  notes: `Hand off to the notebook. Everyone runs Section 0 to get a personal baseline cost. This baseline is what they'll compare each optimization against. Regroup when most people have a number.`,
});
