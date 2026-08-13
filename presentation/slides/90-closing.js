/* ======================================================== 90 · CLOSING
   Recap of the five techniques -> the extension point (as a concept, not
   code) -> a branded thank-you. No HUD; no fragments.
============================================================================ */

Deck.add({
  id: "recap",
  html: `
    <div class="slide-head">
      <div class="kicker">Recap</div>
      <h2>Five levers, one honest meter</h2>
    </div>
    <table class="recap">
      <thead>
        <tr><th>Technique</th><th>Status</th><th>What the meter does</th></tr>
      </thead>
      <tbody>
        ${TW.recapRow('summarization')}
        ${TW.recapRow('prompt-caching')}
        ${TW.recapRow('routing')}
        ${TW.recapRow('context-window')}
        ${TW.recapRow('loop-prevention')}
      </tbody>
    </table>
    <p class="muted" style="font-size:0.82em;margin-top:16px;">Every row is proven the same way: run the task, read the meter, compare before vs after. <b>No estimates.</b></p>
  `,
  notes: `Recap. All five are live and wired into the repo, and all five plug into the SAME extension point. The through-line of the whole session: prove it with real numbers, never claim it.`,
});

Deck.add({
  id: "build-your-own",
  html: `
    <div class="slide-head">
      <div class="kicker">Take it home</div>
      <h2>Add your own optimization</h2>
    </div>
    <div class="icon-rows" style="margin-top:18px;">
      <div class="icon-row wave"><div class="ic">${TW.icon('summarize')}</div><div class="tx"><b>Change what history is sent</b> &mdash; summarize, prune, retrieve.</div></div>
      <div class="icon-row flamingo"><div class="ic">${TW.icon('bolt')}</div><div class="tx"><b>Change the model call itself</b> &mdash; cache, route, guard, tune.</div></div>
      <div class="icon-row turmeric"><div class="ic">${TW.icon('check')}</div><div class="tx"><b>Change the instructions</b> &mdash; style, brevity, output control.</div></div>
    </div>
    <div class="callout" style="margin-top:22px;">
      Pick one hook, register it with <b>one line</b>, switch it on with a flag &mdash; then let the meter settle the argument. <b>The before/after is the deliverable.</b>
    </div>
  `,
  notes: `This is the workshop's payload: everyone leaves able to add an optimization. One of three hooks, one registration line, works in both the REPL and the benchmark. Prove it with /usage; check correctness with --benchmark.`,
});

Deck.add({
  id: "thanks",
  dark: true,
  hideChrome: true,
  html: `
    <div class="center-v" style="position:relative;">
      <div class="eyebrow" style="color:var(--tw-flamingo);font-weight:700;letter-spacing:0.14em;text-transform:uppercase;font-size:0.6em;margin-bottom:1em;">XConf 2026 &middot; Thank you</div>
      <h1 style="color:#fff;font-size:2.6em;max-width:20ch;">Make it work &mdash; then make it cheap.</h1>
      <p class="lead" style="color:#9fb6bd;max-width:46ch;margin-top:0.4em;">Take the base agent, layer on an optimization, and let the meter settle the argument.</p>
      <div style="margin-top:30px;display:flex;gap:44px;flex-wrap:wrap;align-items:flex-end;">
        <div>
          <div style="color:var(--tw-flamingo);font-weight:700;">${TW.speakerByline()}</div>
          <div style="color:#9fb6bd;font-size:0.82em;">Thoughtworks</div>
        </div>
        <div style="font-family:var(--tw-mono);font-size:0.8em;color:#cfe3e7;">
          <div>repo &nbsp;github.com/&lt;your-org&gt;/coding-agent</div>
          <div style="opacity:0.75;">uv run coding-agent --enable &lt;technique&gt;</div>
        </div>
      </div>
      <div style="margin-top:38px;display:flex;align-items:center;gap:36px;">
        <img src="assets/xconf-logo-white.svg" alt="XConf" style="height:52px;" />
        <img src="assets/tw-logo-white.svg" alt="Thoughtworks" style="height:26px;" />
      </div>
    </div>
  `,
  notes: `Close. Thanks, the repo link (replace <your-org>), and the one-liner to enable any technique. Invite them to submit their own optimization as a PR. Take questions.`,
});
