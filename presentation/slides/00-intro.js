/* ============================================================ 00 · INTRO
   Presenters (self-intro)  ->  Title cover  ->  Agenda / how the session runs.
   HUD stays hidden here on purpose; it makes its entrance with the base
   agent, so "look, a live cost meter" lands as a moment.

   >>> EDIT PLACEHOLDERS: search "Presenter One/Two/Three" and the roles /
       owned-topics below. Nothing else needs touching.
============================================================================ */

Deck.add({
  id: "presenters",
  hideHud: true,
  html: `
    <div class="center-v">
      <div class="kicker">XConf 2026 &middot; Hands-on workshop</div>
      <h2>Hi &mdash; we're your facilitators</h2>
      <p class="lead muted" style="max-width:34ch;">Three of us, one live coding agent, and a set of optimizations we'll switch on in front of you.</p>
      <div class="presenters">
        <div class="presenter a">
          <div class="avatar"></div>
          <div class="pname">Presenter One</div>
          <div class="prole">Role / Title &middot; Thoughtworks</div>
          <div class="powns">Summarization &middot; Prompt caching</div>
        </div>
        <div class="presenter b">
          <div class="avatar"></div>
          <div class="pname">Presenter Two</div>
          <div class="prole">Role / Title &middot; Thoughtworks</div>
          <div class="powns">Model selection &amp; routing</div>
        </div>
        <div class="presenter c">
          <div class="avatar"></div>
          <div class="pname">Presenter Three</div>
          <div class="prole">Role / Title &middot; Thoughtworks</div>
          <div class="powns">Context window &middot; Loop prevention</div>
        </div>
      </div>
    </div>
  `,
  notes: `Quick round of hellos. Names, what we each work on, which optimization each of us owns today. Keep it to ~60s total - the repo is the star.`,
});

Deck.add({
  id: "title",
  hideHud: true,
  hideChrome: true,
  html: `
    <div class="cover">
      <div class="band">
        <div class="xmark"><span class="xconf-mark" style="font-size:120px;"><span class="x">x</span>conf</span></div>
      </div>
      <div class="lower">
        <div class="eyebrow">Hands-on workshop &middot; Cost, Tokens &amp; Performance</div>
        <h1>Optimizing LLM&#8209;Powered Applications</h1>
        <div class="byline">
          Presenter One &middot; Presenter Two &middot; Presenter Three
          <span class="role"> &nbsp;|&nbsp; Thoughtworks</span>
        </div>
      </div>
    </div>
  `,
  notes: `The title. Building an LLM app that WORKS is the easy part - making it fast, cheap and production-ready is the real challenge. That's today.`,
});

Deck.add({
  id: "agenda",
  hideHud: true,
  html: `
    <div class="slide-head">
      <div class="kicker">How this session runs</div>
      <h2>Build it, animate it, then run it yourself</h2>
    </div>
    <div class="split top" style="grid-template-columns:1.15fr 0.85fr;">
      <div class="col">
        <p class="lead">For each optimization we follow the same loop:</p>
        <div class="icon-rows">
          <div class="icon-row teal"><div class="ic">${TW.icon('bolt')}</div><div class="tx"><b>See the idea</b> &mdash; one animated slide, almost no text.</div></div>
          <div class="icon-row coral"><div class="ic">${TW.icon('agent')}</div><div class="tx"><b>Run the notebook</b> &mdash; the same Jupyter notebook you have open.</div></div>
          <div class="icon-row amber"><div class="ic">${TW.icon('gauge')}</div><div class="tx"><b>Measure it</b> &mdash; real tokens &amp; cost, before vs after.</div></div>
        </div>
        <p class="muted" style="font-size:0.8em;margin-top:14px;">Watch the meter in the top-right corner all session &mdash; that's real token &amp; cost tracking from the agent, not a mock-up.</p>
      </div>
      <div class="col">
        <div class="visual-panel">
          <div class="kicker" style="margin-bottom:14px;">Five techniques</div>
          <div class="stack-sm" style="font-family:var(--tw-sans);font-size:0.9em;">
            <div><span class="pill live"><span class="dot"></span>live</span> &nbsp;Conversation summarization</div>
            <div><span class="pill wip"><span class="dot"></span>building</span> &nbsp;Prompt optimization &amp; caching</div>
            <div><span class="pill live"><span class="dot"></span>live</span> &nbsp;Model selection &amp; routing</div>
            <div><span class="pill wip"><span class="dot"></span>building</span> &nbsp;Context window optimization</div>
            <div><span class="pill wip"><span class="dot"></span>building</span> &nbsp;Agent loop prevention</div>
          </div>
        </div>
      </div>
    </div>
  `,
  notes: `Set expectations: idea (animation) -> notebook (you run it) -> measure. Two techniques are already wired into the repo (--enable flags); three are in active development - we'll show the design and where they plug in.`,
});
