/* ============================================ 30 · PROMPT OPTIMIZATION & CACHING
   Technique #2 - IN PROGRESS. Concept: most of every request never changes,
   so stop paying full price for it. The demo slide keeps its fragments +
   HUD (optimization showcase); the plan slide is static.
============================================================================ */

Deck.add({
  id: "pc-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:var(--tw-turmeric);">
      <div class="bar"></div>
      <div class="idx">Technique 02</div>
      <h1>Prompt optimization &amp; caching</h1>
      <p>Most of every request is identical each turn. Stop paying full price for the parts that never change.</p>
      <div class="sep-meta">
        <span class="pill wip"><span class="dot"></span>in progress</span>
        <div class="flag">stable prefix &rarr; cache hit</div>
      </div>
    </div>
  `,
  notes: `Presenter One. Two levers here: (1) prompt optimization - a tighter system prompt = fewer input tokens on EVERY call; (2) prompt caching - providers bill a cached prefix at ~10%. Status: wiring it into the base agent now.`,
});

Deck.add({
  id: "pc-concept",
  hud: true,
  tokens: 6150,
  cost: 0.0360,
  html: `
    <div class="slide-head">
      <div class="kicker">02 &middot; Prompt optimization &amp; caching</div>
      <h2>Same prefix, every single call</h2>
    </div>
    <div class="split" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.88em;">
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tw-mist);border-left:8px solid var(--tw-sapphire);">
            <span><b>System prompt</b></span><span style="font-family:var(--tw-mono);">stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tw-mist);border-left:8px solid var(--tw-sapphire);">
            <span><b>Tool definitions</b></span><span style="font-family:var(--tw-mono);">stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tw-mist);border-left:8px solid var(--tw-sapphire);">
            <span><b>Early history</b></span><span style="font-family:var(--tw-mono);">stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tint-flamingo);border-left:8px solid var(--tw-flamingo);">
            <span><b>New message</b></span><span style="font-family:var(--tw-mono);">changes</span>
          </div>
        </div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="fragment fade-in callout" data-fragment-index="0"
               data-cost="0.0378" data-hint="full price on the whole prefix">
            <b>Without caching:</b> the whole stable prefix is re-charged at full price &mdash; every turn.
          </div>
          <div class="fragment fade-in callout" data-fragment-index="1" style="border-left-color:var(--tw-jade);"
               data-cost="0.0384" data-hint="cache hit: prefix billed ~10%"
               data-tokens="6150">
            <b>With a cache hit:</b> the prefix is billed at ~10%. Only the new tokens pay full price.
          </div>
          <div class="fragment fade-in" data-fragment-index="2">
            <div class="bignum"><div class="n">~85%<span class="unit"> less</span></div><div class="lbl">projected input-token cost on cached turns</div></div>
          </div>
        </div>
      </div>
    </div>
  `,
  notes: `Design slide (not yet live). The meter here shows the PROJECTED effect - be explicit that this is the target, not a measured run yet. Point: caching doesn't cut tokens, it cuts the PRICE of the repeated ones - so the token gauge barely moves while cost growth flattens.`,
});

Deck.add({
  id: "pc-plan",
  html: `
    <div class="slide-head">
      <div class="kicker">02 &middot; Where it plugs in</div>
      <h2>Two levers, no loop changes</h2>
    </div>
    <div class="card-grid cols-2" style="margin-top:20px;">
      <div class="tw-card turmeric">
        <div class="cap">Trim the prompt</div>
        <div class="body">Tighter wording, leaner tool docs. Fewer input tokens on <b>every</b> call &mdash; a pure win that compounds with volume.</div>
      </div>
      <div class="tw-card wave">
        <div class="cap">Cache the stable prefix</div>
        <div class="body">Mark the unchanging prefix as cacheable at the API boundary. The provider re-bills it at a fraction of the price.</div>
      </div>
    </div>
    <div class="callout" style="margin-top:20px;">
      The groundwork is already live: <b>cache-friendly prompt construction</b> (next) builds the byte-stable prefix a cache can actually reuse.
    </div>
  `,
  notes: `Reassure the room this isn't special-cased: it's the same plug-in pattern every optimization uses. Prompt trimming is an instruction change; caching wraps the model call. The deterministic construction it relies on is already implemented - next section.`,
});
