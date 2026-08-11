/* ============================================= 50 · CONTEXT WINDOW OPTIMIZATION
   Technique #4 - IN PROGRESS. Distinct from summarization: instead of
   compressing old turns into prose, SELECT what's relevant and prune the
   rest. The concept demo keeps fragments + HUD; the plan slide is static.
============================================================================ */

Deck.add({
  id: "cw-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:var(--tw-amethyst);">
      <div class="bar"></div>
      <div class="idx">Technique 04</div>
      <h1>Context window optimization</h1>
      <p>Summarization compresses the past. This is about <em>relevance</em> &mdash; only include what this step actually needs.</p>
      <div class="sep-meta">
        <span class="pill wip"><span class="dot"></span>in progress</span>
        <div class="flag">keep the signal, drop the noise</div>
      </div>
    </div>
  `,
  notes: `Presenter Three. The trap: a single 900-line file dump or a stale tool output rides along in every future call. Context-window optimization prunes by relevance so the window stays small and sharp.`,
});

Deck.add({
  id: "cw-concept",
  hud: true,
  tokens: 9800,
  cost: 0.0400,
  html: `
    <div class="slide-head">
      <div class="kicker">04 &middot; Context window optimization</div>
      <h2>Not everything deserves a seat</h2>
    </div>
    <div class="split top" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.85em;">
          <div style="display:flex;justify-content:space-between;gap:12px;padding:13px 17px;border-radius:10px;background:var(--tw-mist);"><span>Current task &amp; recent steps</span><span style="color:var(--tw-jade);font-weight:800;">keep</span></div>
          <div class="fragment fade-out" data-fragment-index="0" style="display:flex;justify-content:space-between;gap:12px;padding:13px 17px;border-radius:10px;background:var(--tint-flamingo);"><span>900-line file dump, read 6 turns ago</span><span style="color:var(--tw-flamingo);font-weight:800;">prune</span></div>
          <div class="fragment fade-out" data-fragment-index="0" style="display:flex;justify-content:space-between;gap:12px;padding:13px 17px;border-radius:10px;background:var(--tint-flamingo);"><span>Stale command output, now irrelevant</span><span style="color:var(--tw-flamingo);font-weight:800;">prune</span></div>
          <div style="display:flex;justify-content:space-between;gap:12px;padding:13px 17px;border-radius:10px;background:var(--tw-mist);"><span>Files touched this task (paths only)</span><span style="color:var(--tw-jade);font-weight:800;">keep</span></div>
        </div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="fragment fade-in callout" data-fragment-index="0"
               data-tokens="4200" data-cost="0.0400" data-hint="prune irrelevant -> window shrinks">
            <b>Prune by relevance.</b> Drop bulky, stale content the next step won't use &mdash; the window shrinks without losing the thread.
          </div>
          <div class="fragment fade-in" data-fragment-index="1">
            <div class="bignum"><div class="n">~57%<span class="unit"> smaller</span></div><div class="lbl">projected context on a file-heavy task</div></div>
          </div>
          <div class="fragment fade-in callout" data-fragment-index="2" style="border-left-color:var(--tw-sapphire);">
            Pairs with retrieval: re-fetch a file on demand instead of carrying it forever.
          </div>
        </div>
      </div>
    </div>
  `,
  notes: `Design slide (not yet live). Contrast clearly with summarization: summarization = compress old turns to prose; context optimization = SELECT relevant items and drop the rest, often re-fetching on demand. The token gauge drops immediately when we prune the file dump.`,
});

Deck.add({
  id: "cw-plan",
  html: `
    <div class="slide-head">
      <div class="kicker">04 &middot; Where it plugs in</div>
      <h2>Same hook as summarization &mdash; with a catch</h2>
    </div>
    <div class="card-grid cols-2" style="margin-top:20px;">
      <div class="tw-card wave"><div class="cap">It decides what gets sent</div><div class="body">The same plug-in point summarization uses. Here it <b>filters by relevance</b> instead of compressing into prose.</div></div>
      <div class="tw-card flamingo"><div class="cap">Only one policy can own history</div><div class="body">The base agent <b>refuses to start</b> if two optimizations both claim it &mdash; combining them is a real design decision, not last-writer-wins.</div></div>
    </div>
    <div class="callout" style="margin-top:20px;">
      The open question we're working through: <b>compress</b> and <b>prune</b> as one coordinated policy, or a pipeline of two.
    </div>
  `,
  notes: `Presenter Three. Honest engineering note straight from the repo: history_policy has a single owner by design (ConflictingOptimizationsError). So context optimization + summarization can't both just be switched on - they need one combined policy. That's exactly what we're building.`,
});
