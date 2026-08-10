/* ============================================ 30 · PROMPT OPTIMIZATION & CACHING
   Technique #2 - IN PROGRESS. We show the design + where it plugs in, and
   the projected HUD effect. Two ideas: trim the prompt, and cache the stable
   prefix so repeated input tokens are billed at a fraction.
============================================================================ */

Deck.add({
  id: "pc-sep",
  hideHud: true,
  html: `
    <div class="separator">
      <div class="txt">
        <div class="idx">Technique 02</div>
        <h1>Prompt optimization<br/>&amp; caching</h1>
        <p>Most of every request is identical each turn: the system prompt and tool schemas. Stop paying full price for the parts that never change.</p>
        <div style="margin-top:18px;"><span class="pill wip"><span class="dot"></span>in progress</span></div>
      </div>
      <div class="visual amber">
        <div style="text-align:center;color:#fff;">
          <div style="font-size:3em;">${TW.icon('cache')}</div>
          <div style="font-family:var(--tw-mono);font-size:0.72em;margin-top:12px;opacity:0.9;">stable prefix &rarr; cache hit</div>
        </div>
      </div>
    </div>
  `,
  notes: `Presenter One. Two levers here: (1) prompt optimization - a tighter system prompt = fewer input tokens on EVERY call; (2) prompt caching - providers bill a cached prefix at ~10%. Status: wiring it into the base agent now.`,
});

Deck.add({
  id: "pc-concept",
  hideHud: false,
  tokens: 6150,
  cost: 0.0360,
  html: `
    <div class="slide-head">
      <div class="kicker">02 &middot; Prompt optimization &amp; caching</div>
      <h2>Same prefix, every single call</h2>
    </div>
    <div class="split" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.82em;">
          <div style="display:flex;justify-content:space-between;padding:11px 14px;border-radius:9px;background:var(--tw-card);border-left:6px solid var(--tw-teal);">
            <span><b>System prompt</b></span><span style="font-family:var(--tw-mono);">640 tok &middot; stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:11px 14px;border-radius:9px;background:var(--tw-card);border-left:6px solid var(--tw-teal);">
            <span><b>Tool schemas</b></span><span style="font-family:var(--tw-mono);">1,120 tok &middot; stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:11px 14px;border-radius:9px;background:var(--tw-card);border-left:6px solid var(--tw-teal);">
            <span><b>Early history</b></span><span style="font-family:var(--tw-mono);">4,300 tok &middot; stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:11px 14px;border-radius:9px;background:#fdeef1;border-left:6px solid var(--tw-coral);">
            <span><b>New message</b></span><span style="font-family:var(--tw-mono);">90 tok &middot; changes</span>
          </div>
        </div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="fragment fade-in callout" data-fragment-index="0"
               data-cost="0.0378" data-hint="full price on the whole prefix">
            <b>Without caching:</b> all 6,060 stable tokens are re-charged at full input price &mdash; every turn.
          </div>
          <div class="fragment fade-in callout" data-fragment-index="1" style="border-left-color:var(--tw-green);"
               data-cost="0.0384" data-hint="cache hit: prefix billed ~10%"
               data-tokens="6150">
            <b>With a cache hit:</b> the 6,060-token prefix is billed at ~10%. Only the 90 new tokens pay full price.
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
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">Where it plugs in</div>
      <h2>Two hooks, no loop changes</h2>
    </div>
    <div class="card-grid cols-2">
      <div class="tw-card amber">
        <div class="cap">Prompt optimization &rarr; system_prompt_suffix / trimmed prompt</div>
        <div class="body">Tighten wording, cut redundant tool docs. Fewer input tokens on every call &mdash; a pure win that compounds with volume.</div>
      </div>
      <div class="tw-card teal">
        <div class="cap">Prompt caching &rarr; wrap_llm_client</div>
        <div class="body">Mark the stable prefix as cacheable at the API boundary; the decorator adds cache breakpoints without the agent loop knowing.</div>
      </div>
    </div>
    <div class="callout" style="margin-top:16px;">
      Both are standard <code>OptimizationBundle</code> hooks &mdash; the same extension point summarization and routing use. <span class="pill wip"><span class="dot"></span>building now</span>
    </div>
  `,
  notes: `Reassure the room this isn't special-cased: it's the same bundle pattern. Prompt trimming is a suffix/prompt edit; caching is an LLMClient wrapper that inserts cache breakpoints. Coming to the notebook soon.`,
});
