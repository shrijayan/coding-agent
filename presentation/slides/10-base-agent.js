/* ===================================================== 10 · BASE CODING AGENT
   What the repo is, the agent loop as ONE picture, and the cost meter's
   entrance. Concept-first: the loop is a diagram, not code. Only the
   cost-tracking demo uses fragments + the HUD.
============================================================================ */

Deck.add({
  id: "base-intro",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:var(--tw-sapphire);">
      <div class="bar"></div>
      <div class="idx">Our starting point</div>
      <h1>A tiny coding agent, built from scratch</h1>
      <p>A chat loop backed by an LLM, with real tools that act on your machine. Everything today is an optimization <em>on top of this</em>.</p>
      <div class="sep-meta"><div class="flag">read &middot; write &middot; edit &middot; bash &middot; list_files</div></div>
    </div>
  `,
  notes: `This is the shared "Base Agent". Small on purpose - you can read the whole thing (~1,500 lines). The point of the workshop: everyone layers one optimization onto this same base and proves it helps with real numbers.`,
});

Deck.add({
  id: "agent-loop",
  html: `
    <div class="slide-head">
      <div class="kicker">The base agent</div>
      <h2>The whole system is one loop</h2>
    </div>
    <div style="display:flex;flex-direction:column;gap:22px;height:calc(100% - 110px);justify-content:center;">
      <div class="flow">
        <div class="node">
          <div style="font-size:1.5em;color:var(--tw-flamingo);">${TW.icon('agent')}</div>
          <div class="nt">You ask</div>
          <div class="ns">a message enters the loop</div>
        </div>
        <div class="arrow">&rarr;</div>
        <div class="node dark">
          <div style="font-size:1.5em;">${TW.icon('bolt')}</div>
          <div class="nt">Model call</div>
          <div class="ns">history + tools sent</div>
        </div>
        <div class="arrow">&rarr;</div>
        <div class="node">
          <div style="font-size:1.5em;color:var(--tw-turmeric);">${TW.icon('route')}</div>
          <div class="nt">Answer or act?</div>
          <div class="ns">text, or a tool request</div>
        </div>
        <div class="arrow">&rarr;</div>
        <div class="node">
          <div style="font-size:1.5em;color:var(--tw-jade);">${TW.icon('check')}</div>
          <div class="nt">Run tools</div>
          <div class="ns">edit files, run commands</div>
        </div>
        <div class="arrow cycle" style="color:var(--tw-sapphire);"><span>&#8634;</span></div>
        <div class="node">
          <div style="font-size:1.5em;color:var(--tw-flamingo);">${TW.icon('loop')}</div>
          <div class="nt">Feed back</div>
          <div class="ns">result returns to the model</div>
        </div>
      </div>
      <div class="callout" style="font-size:0.95em;">
        One user question = <b>many model calls</b>. Every trip around the loop is a real, paid API call. <b>That's what we optimize.</b>
      </div>
    </div>
  `,
  notes: `Walk the five steps - they're all on screen already, just point. Emphasise: the tool loop makes MANY model calls per user turn, not one. So "cost per turn" is really "sum of every call in that turn" - important later for routing.`,
});

Deck.add({
  id: "cost-tracking",
  hud: true,
  tokens: 1850,
  cost: 0.0,
  html: `
    <div class="slide-head">
      <div class="kicker">Built-in measurement</div>
      <h2>It counts every real token &amp; dollar</h2>
    </div>
    <div class="split top" style="grid-template-columns:1.1fr 0.9fr;">
      <div class="col">
        <p class="lead">Token counts come only from the provider's real response &mdash; <b>never estimated</b>.</p>
        <div class="stack-sm" style="margin-top:14px;font-size:0.95em;">
          <div class="fragment fade-in" data-fragment-index="0" data-tokens="1850" data-cost="0.0000">
            <span class="pill planned"><span class="dot"></span>fresh session</span> &nbsp; the meter starts at zero &#8599;
          </div>
          <div class="fragment fade-in" data-fragment-index="1" data-tokens="6300" data-cost="0.0058" data-hint="one turn = several tool-loop calls">
            <b>Turn 1</b> &mdash; a few tool-loop calls. Watch the meter move.
          </div>
          <div class="fragment fade-in" data-fragment-index="2" data-tokens="11200" data-cost="0.0121" data-hint="history keeps growing every turn">
            <b>Turn 2</b> &mdash; history grows, so the next call is bigger&hellip; and pricier.
          </div>
        </div>
        <div class="fragment fade-in callout" data-fragment-index="3" style="margin-top:18px;">
          <b>This meter is how every optimization gets judged</b> &mdash; before vs after, no hand-waving.
        </div>
      </div>
      <div class="col">
        <div class="visual-panel" style="justify-content:flex-start;">
          <div class="kicker" style="margin-bottom:14px;">Meet the meter &#8599;</div>
          <ul style="font-size:0.88em;color:var(--tw-ink-soft);">
            <li style="margin-bottom:0.7em;"><b>Context tokens</b> &mdash; how big the next call is.</li>
            <li><b>Session cost</b> &mdash; cumulative $ spent. Only ever goes up.</li>
          </ul>
          <p style="font-size:0.8em;color:var(--tw-muted);margin-top:10px;">Good optimizations pull tokens <b>down</b> while barely moving cost <b>up</b>.</p>
        </div>
      </div>
    </div>
  `,
  notes: `THE METER APPEARS NOW - this is its entrance. Advance the fragments slowly so the room notices the numbers tween. Key line: tokens are never estimated - only real provider counts. The whole workshop is trustworthy because of this.`,
});

Deck.add({
  id: "base-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Run the base agent</h2>
      <p class="lead" style="max-width:44ch;">Open the notebook and run the first section: a plain agent, no optimizations. Note your baseline tokens &amp; cost.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Baseline &mdash; the un-optimized agent&rdquo;</div>
          <div class="s">Run the cells, give it a small task, then read the token &amp; cost total.</div>
        </div>
        <div class="nb-cmd">uv run coding-agent</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">Keep your baseline number &mdash; every optimization today is measured against it.</p>
    </div>
  `,
  notes: `Hand off to the notebook. Everyone runs Section 0 to get a personal baseline cost. This baseline is what they'll compare each optimization against. Regroup when most people have a number.`,
});
