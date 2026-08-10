/* ============================================= 50 · CONTEXT WINDOW OPTIMIZATION
   Technique #4 - IN PROGRESS. Distinct from summarization: instead of
   compressing old turns into prose, SELECT what's actually relevant and
   prune the rest (huge tool dumps, stale file reads) to stay lean.
============================================================================ */

Deck.add({
  id: "cw-sep",
  hideHud: true,
  html: `
    <div class="separator">
      <div class="txt">
        <div class="idx">Technique 04</div>
        <h1>Context window<br/>optimization</h1>
        <p>Summarization compresses the past. This is about <em>relevance</em> &mdash; only include what this step actually needs.</p>
        <div style="margin-top:18px;"><span class="pill wip"><span class="dot"></span>in progress</span></div>
      </div>
      <div class="visual grad">
        <div style="text-align:center;color:#fff;">
          <div style="font-size:3em;">${TW.icon('context')}</div>
          <div style="font-family:var(--tw-mono);font-size:0.72em;margin-top:12px;opacity:0.9;">keep the signal, drop the noise</div>
        </div>
      </div>
    </div>
  `,
  notes: `Presenter Three. The trap: a single 900-line file dump or a stale tool output rides along in every future call. Context-window optimization prunes by relevance so the window stays small and sharp.`,
});

Deck.add({
  id: "cw-concept",
  hideHud: false,
  tokens: 9800,
  cost: 0.0400,
  html: `
    <div class="slide-head">
      <div class="kicker">04 &middot; Context window optimization</div>
      <h2>Not everything deserves a seat</h2>
    </div>
    <div class="split top" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.8em;">
          <div style="display:flex;justify-content:space-between;padding:10px 14px;border-radius:9px;background:var(--tw-card);"><span>Current task &amp; recent steps</span><span style="color:var(--tw-green);font-weight:700;">keep</span></div>
          <div class="fragment fade-out" data-fragment-index="0" style="display:flex;justify-content:space-between;padding:10px 14px;border-radius:9px;background:#fdeef1;"><span>900-line file dump (read 6 turns ago)</span><span style="color:var(--tw-coral-600);font-weight:700;">prune</span></div>
          <div class="fragment fade-out" data-fragment-index="0" style="display:flex;justify-content:space-between;padding:10px 14px;border-radius:9px;background:#fdeef1;"><span>Stale <code>bash</code> output, now irrelevant</span><span style="color:var(--tw-coral-600);font-weight:700;">prune</span></div>
          <div style="display:flex;justify-content:space-between;padding:10px 14px;border-radius:9px;background:var(--tw-card);"><span>Files touched this task (paths only)</span><span style="color:var(--tw-green);font-weight:700;">keep</span></div>
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
          <div class="fragment fade-in callout" data-fragment-index="2" style="border-left-color:var(--tw-teal);">
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
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">Where it plugs in</div>
      <h2>A HistoryPolicy &mdash; with a caveat</h2>
    </div>
    <div class="card-grid cols-2">
      <div class="tw-card teal"><div class="cap">Hook: history_policy.prepare()</div><div class="body">Same hook summarization uses &mdash; it decides what actually gets sent. Here it filters/prunes by relevance instead of compressing.</div></div>
      <div class="tw-card coral"><div class="cap">Only one history owner</div><div class="body">The base agent raises <code>ConflictingOptimizationsError</code> if two optimizations both claim <code>history_policy</code>. Combining with summarization is a real design decision, not last-writer-wins.</div></div>
    </div>
    <div class="callout" style="margin-top:16px;">
      So the open question we're working through: <b>compress</b> and <b>prune</b> as one coordinated policy, or a pipeline of two. <span class="pill wip"><span class="dot"></span>designing now</span>
    </div>
  `,
  notes: `Presenter Three. Honest engineering note straight from the repo: history_policy has a single owner by design. So context optimization + summarization can't both just be switched on - they need one combined policy. That's exactly what we're building.`,
});
