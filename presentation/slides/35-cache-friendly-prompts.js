/* ======================================= 35 · CACHE-FRIENDLY PROMPT CONSTRUCTION
   Technique #2b - LIVE in the repo. Caching is what the PROVIDER does; this
   is how WE build the prompt so a cache can actually reuse it. The concept
   demo keeps its fragments + HUD; the "how" slide is a static visual.
============================================================================ */

Deck.add({
  id: "cf-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:var(--tw-sapphire);">
      <div class="bar"></div>
      <div class="idx">Technique 02b</div>
      <h1>Cache-friendly prompts</h1>
      <p>A cache can only reuse a prefix that is <b>byte-identical</b> every turn. So build the prompt deterministically &mdash; stable parts first, churn last.</p>
      <div class="sep-meta">
        <span class="pill live"><span class="dot"></span>live in the repo</span>
        <div class="flag">--enable cache-friendly-prompts</div>
      </div>
    </div>
  `,
  notes: `Presenter One. Prompt caching (previous section) is provider-side: THEY bill a repeated prefix at a fraction. But that only fires if the bytes match exactly. This technique is our side of that deal: construct the prompt so the stable prefix never wobbles - deterministic ordering, canonical JSON, normalized whitespace. Provider-agnostic.`,
});

Deck.add({
  id: "cf-concept",
  hud: true,
  tokens: 6150,
  cost: 0.0360,
  html: `
    <div class="slide-head">
      <div class="kicker">02b &middot; Cache-friendly prompts</div>
      <h2>Layer by volatility, not by accident</h2>
    </div>
    <div class="split" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.88em;">
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tw-mist);border-left:8px solid var(--tw-sapphire);">
            <span><b>System prompt &middot; tools</b></span><span style="font-family:var(--tw-mono);">stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tw-mist);border-left:8px solid var(--tw-sapphire);">
            <span><b>Repository metadata</b></span><span style="font-family:var(--tw-mono);">stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tint-turmeric);border-left:8px solid var(--tw-turmeric);">
            <span><b>Summary &middot; active files</b></span><span style="font-family:var(--tw-mono);">semi-stable</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:14px 18px;border-radius:10px;background:var(--tint-flamingo);border-left:8px solid var(--tw-flamingo);">
            <span><b>Latest message &middot; results</b></span><span style="font-family:var(--tw-mono);">dynamic</span>
          </div>
        </div>
        <div class="callout" style="margin-top:16px;font-size:0.82em;">Stable &rarr; semi-stable &rarr; dynamic. <b>Always in that order.</b></div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="fragment fade-in callout" data-fragment-index="0"
               data-hint="one stray reorder defeats the cache">
            <b>Determinism is the whole game.</b> Same content must mean the same bytes &mdash; sorted tools, canonical formatting, no timestamps.
          </div>
          <div class="fragment fade-in callout" data-fragment-index="1" style="border-left-color:var(--tw-jade);"
               data-hint="prefix grows as the turn stays stable">
            <b>Reuse compounds.</b> As the conversation grows, more of every request is a byte-identical prefix a cache can reuse.
          </div>
          <div class="fragment fade-in" data-fragment-index="2">
            <div class="bignum"><div class="n">~95%<span class="unit"> reuse</span></div><div class="lbl">of the prompt is an unchanged prefix by turn N</div></div>
          </div>
        </div>
      </div>
    </div>
  `,
  notes: `The build order IS the optimization. STABLE (system prompt, tool defs, repo metadata) never changes -> goes first. SEMI-STABLE (summary, active files) changes occasionally -> middle. DYNAMIC (latest message, tool results) changes every send -> last. Determinism guarantees the stable prefix hashes the same every turn; the reuse % is measured in bytes, never estimated tokens.`,
});

Deck.add({
  id: "cf-how",
  html: `
    <div class="slide-head">
      <div class="kicker">02b &middot; How it's built</div>
      <h2>Build &rarr; canonicalize &rarr; verify</h2>
    </div>
    <div class="flow" style="margin-top:24px;">
      <div class="node">
        <div style="font-size:1.5em;color:var(--tw-wave);">${TW.icon('stack')}</div>
        <div class="nt">Builder</div>
        <div class="ns">assembles layers, stable prefix guaranteed first</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="node">
        <div style="font-size:1.5em;color:var(--tw-turmeric);">${TW.icon('shield')}</div>
        <div class="nt">Serializer</div>
        <div class="ns">identical content &rarr; identical bytes, then fingerprint it</div>
      </div>
      <div class="arrow">&rarr;</div>
      <div class="node">
        <div style="font-size:1.5em;color:var(--tw-jade);">${TW.icon('check')}</div>
        <div class="nt">Verify</div>
        <div class="ns">one stable fingerprint across every call = cache-ready</div>
      </div>
    </div>
    <div class="callout" style="margin-top:26px;">
      Works with <b>any provider</b> &mdash; the construction is ours; provider-specific caching plugs in at the edge without touching the core.
    </div>
  `,
  notes: `Presenter One. Same plug-in pattern as everything else - it wraps the model call, zero loop changes. The pieces: a builder (assembly + stable-before-dynamic invariant), a serializer (deterministic bytes + hash), and a provider seam so vendor caching plugs in later. Instrumentation is honest: input tokens are the provider's real number; reuse % is a byte fact.`,
});

Deck.add({
  id: "cf-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Watch the prefix stay put</h2>
      <p class="lead" style="max-width:46ch;">Run a multi-turn task and watch the stable-prefix fingerprint stay identical while reuse climbs turn over turn.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Optimization 2b &mdash; Cache-friendly prompts&rdquo;</div>
          <div class="s">Run the shared task set, then check the cache report for prefix reuse.</div>
        </div>
        <div class="nb-cmd">--enable cache-friendly-prompts</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">One stable fingerprint across every call is the win &mdash; it means a cache has something byte-stable to reuse.</p>
    </div>
  `,
  notes: `Hands on. Everyone runs the multi-turn task with cache-friendly construction on and reads /cache: distinct stable hashes should be 1 (the prefix never moved), avg prefix reuse rises across sends. This is the groundwork any real prompt-cache pass builds on.`,
});
