/* ============================================================ 00 · INTRO
   Title cover (official template look) -> facilitators -> how the session
   runs. No HUD here - it debuts with the cost-tracking demo. No fragments:
   each slide appears whole, then we talk.
============================================================================ */

Deck.add({
  id: "title",
  hideChrome: true,
  html: `
    <div class="cover">
      <div class="band">
        <div class="cell"><img src="assets/fluid-gradient.png" alt="" /></div>
        <div class="cell"><img src="assets/x-sculpture.png" alt="XConf X sculpture" style="object-position:center 60%;" /></div>
      </div>
      <div class="lower">
        <div class="eyebrow">XConf 2026 &middot; Hands-on workshop</div>
        <h1>Optimizing LLM&#8209;Powered Applications</h1>
        <div class="byline">
          ${TW.speakerByline()}
          <span class="role"> &nbsp;|&nbsp; Thoughtworks</span>
        </div>
        <div style="position:absolute;right:8px;bottom:10px;"><img src="assets/xconf-logo.svg" alt="XConf" style="height:56px;" /></div>
        <div class="qr-wrap">
          <img src="assets/colab-notebook-qr.png" alt="Open the notebook in Colab" />
          <span>Open the notebook</span>
        </div>
      </div>
    </div>
  `,
  notes: `The title. Building an LLM app that WORKS is the easy part - making it fast, cheap and production-ready is the real challenge. That's today.`,
});

Deck.add({
  id: "presenters",
  html: `
    <div class="center-v">
      <div class="kicker">XConf 2026 &middot; Hands-on workshop</div>
      <h2>Hi &mdash; we're your facilitators</h2>
      <p class="lead muted" style="max-width:40ch;">Three of us, one live coding agent, and a set of optimizations we'll switch on in front of you.</p>
      <div class="presenters">
        ${TW.presenterCards()}
      </div>
    </div>
  `,
  notes: `Quick round of hellos. Names, what we each work on, which optimization each of us owns today. Keep it to ~60s total - the repo is the star.`,
});

Deck.add({
  id: "agenda",
  html: `
    <div class="slide-head">
      <div class="kicker">How this session runs</div>
      <h2>See it, run it, measure it</h2>
    </div>
    <div class="split top qr-split">
      <div class="col">
        <div class="icon-rows">
          <div class="icon-row wave"><div class="ic">${TW.icon('bolt')}</div><div class="tx"><b>See the idea</b> &mdash; one animated slide, almost no text.</div></div>
          <div class="icon-row flamingo"><div class="ic">${TW.icon('agent')}</div><div class="tx"><b>Run the notebook</b> &mdash; the same Jupyter notebook you have open.</div></div>
          <div class="icon-row turmeric"><div class="ic">${TW.icon('gauge')}</div><div class="tx"><b>Measure it</b> &mdash; real tokens &amp; cost, before vs after.</div></div>
        </div>
        <p class="muted" style="font-size:0.82em;margin-top:18px;">During the demos, a live token &amp; cost meter appears top-right &mdash; real tracking from the agent, not a mock-up.</p>
      </div>
      <div class="col qr-col">
        <div class="qr-box">
          <img src="assets/colab-notebook-qr.png" alt="Scan to open the notebook in Colab" />
        </div>
        <span class="qr-label">Scan to open the notebook</span>
      </div>
    </div>
  `,
  notes: `Set expectations: idea (animation) -> notebook (you run it) -> measure. All five techniques are live and wired into the repo - each one runs end-to-end in the notebook you have open.`,
});
