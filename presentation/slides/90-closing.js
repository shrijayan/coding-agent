/* ======================================================== 90 · CLOSING
   Recap of the five techniques  ->  how to add your own (the extension
   point)  ->  a branded thank-you. HUD is retired here; the demos are done.
============================================================================ */

Deck.add({
  id: "recap",
  hideHud: true,
  html: `
    <div class="slide-head">
      <div class="kicker">Recap</div>
      <h2>Five levers, one honest meter</h2>
    </div>
    <table class="recap">
      <thead>
        <tr><th>Technique</th><th>Plugs in via</th><th>Status</th><th>What the meter does</th></tr>
      </thead>
      <tbody>
        <tr><td><b>Conversation summarization</b></td><td><code>history_policy</code></td><td><span class="pill live"><span class="dot"></span>live</span></td><td>tokens &darr;&darr; per turn, one-off summarize cost</td></tr>
        <tr><td><b>Prompt optimization &amp; caching</b></td><td><code>suffix</code> / <code>wrap_llm_client</code></td><td><span class="pill wip"><span class="dot"></span>building</span></td><td>cost growth flattens on repeated prefixes</td></tr>
        <tr><td><b>Model selection &amp; routing</b></td><td><code>wrap_llm_client</code></td><td><span class="pill live"><span class="dot"></span>live</span></td><td>cost &darr; &mdash; cheap model does the easy work</td></tr>
        <tr><td><b>Context window optimization</b></td><td><code>history_policy</code></td><td><span class="pill wip"><span class="dot"></span>building</span></td><td>tokens &darr; by pruning irrelevant context</td></tr>
        <tr><td><b>Agent loop prevention</b></td><td><code>wrap_llm_client</code></td><td><span class="pill wip"><span class="dot"></span>building</span></td><td>caps runaway cost when the agent spins</td></tr>
      </tbody>
    </table>
    <p class="muted" style="font-size:0.82em;margin-top:14px;">Every row is proven the same way: run the task, read <code>/usage</code>, compare before vs after. No estimates.</p>
  `,
  notes: `Recap. Note two are live, three are in active development - and all five plug into the SAME extension point. The through-line of the whole session: prove it with real numbers, never claim it.`,
});

Deck.add({
  id: "build-your-own",
  hideHud: true,
  html: `
    <div class="slide-head">
      <div class="kicker">optimizations/bundle.py</div>
      <h2>Add your own in three lines</h2>
    </div>
    <div class="split top" style="grid-template-columns:1.05fr 0.95fr;">
      <div class="col">
        <div class="code-panel">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="fn">optimizations/your_thing.py</span></div>
          <pre><code class="language-python" data-trim>def build() -> OptimizationBundle:
    return OptimizationBundle(
        # pick the hook your idea needs:
        history_policy=YourPolicy(),        # what history to send
        # wrap_llm_client=YourWrapper,      # change the call itself
        # system_prompt_suffix="...",       # just an instruction
    )

# register once:
AVAILABLE_OPTIMIZATIONS["your-thing"] = build</code></pre>
        </div>
      </div>
      <div class="col">
        <div class="icon-rows">
          <div class="icon-row teal"><div class="ic">${TW.icon('summarize')}</div><div class="tx"><b>history_policy</b> &mdash; change what history is sent (summarize, prune, retrieve).</div></div>
          <div class="icon-row coral"><div class="ic">${TW.icon('bolt')}</div><div class="tx"><b>wrap_llm_client</b> &mdash; change the call (cache, route, guard, params).</div></div>
          <div class="icon-row amber"><div class="ic">${TW.icon('check')}</div><div class="tx"><b>system_prompt_suffix</b> &mdash; just an instruction (style, brevity).</div></div>
        </div>
        <div class="callout" style="margin-top:12px;"><code>--enable your-thing</code> in the CLI <em>and</em> the benchmark &mdash; then compare <code>/usage</code>. That before/after is the deliverable.</div>
      </div>
    </div>
  `,
  notes: `This is the workshop's payload: everyone leaves able to add an optimization. One of three hooks, one registration line, works in both the REPL and the benchmark. Prove it with /usage; check correctness with --benchmark.`,
});

Deck.add({
  id: "thanks",
  dark: true,
  hideHud: true,
  hideChrome: true,
  html: `
    <div class="center-v">
      <div class="eyebrow" style="color:var(--tw-coral);font-weight:700;letter-spacing:0.14em;text-transform:uppercase;font-size:0.6em;margin-bottom:1em;">XConf 2026 &middot; Thank you</div>
      <h1 style="color:#fff;font-size:2.6em;max-width:20ch;">Make it work &mdash; then make it cheap.</h1>
      <p class="lead" style="color:#9fb6bd;max-width:46ch;margin-top:0.4em;">Take the base agent, layer on an optimization, and let the meter settle the argument.</p>
      <div style="margin-top:26px;display:flex;gap:40px;flex-wrap:wrap;align-items:flex-end;">
        <div>
          <div style="color:var(--tw-coral);font-weight:700;">Presenter One &middot; Presenter Two &middot; Presenter Three</div>
          <div style="color:#9fb6bd;font-size:0.82em;">Thoughtworks</div>
        </div>
        <div style="font-family:var(--tw-mono);font-size:0.82em;color:#cfe3e7;">
          <div>repo &nbsp;github.com/&lt;your-org&gt;/coding-agent</div>
          <div style="opacity:0.75;">uv run coding-agent --enable &lt;technique&gt;</div>
        </div>
      </div>
      <div style="margin-top:34px;"><span class="tw-logo" style="color:#fff;font-size:26px;"><span class="slash" style="color:var(--tw-coral);">/</span>thoughtworks</span></div>
    </div>
  `,
  notes: `Close. Thanks, the repo link (replace <your-org>), and the one-liner to enable any technique. Invite them to submit their own optimization as a PR. Take questions.`,
});
