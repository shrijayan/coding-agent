/* ============================================ 30 · PROMPT OPTIMIZATION & CACHING
   Technique #2 - LIVE in the repo. Two levers: (a) prompt optimization - a
   family of FIVE techniques, all live (context pruning, summarization, tool
   filtering, prompt compression, deduplication); (b) prompt caching -
   --enable cache-friendly-prompts builds the byte-stable prefix a cache
   needs (measured on the next slide); ProviderCacheAdapter is the wired seam
   a vendor-specific cache hint plugs into. The demo slide keeps its
   fragments + HUD (optimization showcase).
============================================================================ */

Deck.add({
  id: "pc-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:${TW.techAccent('prompt-caching')};">
      <div class="bar"></div>
      <div class="idx">${TW.techIdx('prompt-caching')}</div>
      <h1>${TW.techTitle('prompt-caching')}</h1>
      <p>Most of every request is identical each turn. Send fewer tokens &mdash; and stop paying full price for the ones that must repeat.</p>
      ${TW.techMeta('prompt-caching')}
    </div>
  `,
  notes: `Krishna Chaitanya. Two levers here: (1) prompt optimization - not one trick but a FAMILY OF FIVE techniques, all live in the repo: context pruning (context-window), conversation summarization (conversation-summary), tool filtering, prompt compression, deduplication; (2) prompt caching - providers bill a cached prefix at ~10%. What's live today on the caching side: the deterministic, byte-stable prefix construction (cache-friendly-prompts, next section) that any provider cache needs before it can reuse anything - plus the ProviderCacheAdapter seam a vendor-specific cache hint drops into.`,
});

Deck.add({
  id: "pc-family",
  html: `
    <div class="slide-head">
      <div class="kicker">02 &middot; Prompt optimization</div>
      <h2>Not one trick &mdash; five techniques</h2>
    </div>
    <div class="card-grid cols-3" style="margin-top:18px;font-size:0.92em;">
      <div class="tw-card sapphire">
        <div class="cap">Context pruning</div>
        <div class="body">Remove irrelevant conversation history &mdash; stale bulky tool output becomes a short placeholder.<br><span style="font-family:var(--tw-mono);font-size:0.85em;">--enable context-window</span></div>
      </div>
      <div class="tw-card sapphire">
        <div class="cap">Conversation summarization</div>
        <div class="body">Replace older messages with a concise running summary; recent turns stay verbatim.<br><span style="font-family:var(--tw-mono);font-size:0.85em;">--enable conversation-summary</span></div>
      </div>
      <div class="tw-card turmeric">
        <div class="cap">Tool filtering</div>
        <div class="body">Expose only tools relevant to the current request &mdash; withheld safely, never mid-use.<br><span style="font-family:var(--tw-mono);font-size:0.85em;">--enable tool-filtering</span></div>
      </div>
      <div class="tw-card turmeric">
        <div class="cap">Prompt compression</div>
        <div class="body">Rewrite long instructions into shorter equivalents without losing meaning &mdash; hand-tightened, deterministic.<br><span style="font-family:var(--tw-mono);font-size:0.85em;">--enable prompt-compression</span></div>
      </div>
      <div class="tw-card turmeric">
        <div class="cap">Deduplication</div>
        <div class="body">Never repeat identical instructions or content &mdash; later exact copies become a marker pointing at the first.<br><span style="font-family:var(--tw-mono);font-size:0.85em;">--enable deduplication</span></div>
      </div>
      <div class="tw-card wave">
        <div class="cap">All five compose</div>
        <div class="body">Every removal is deterministic and local &mdash; never a model call that spends tokens to save tokens, never an estimate.</div>
      </div>
    </div>
  `,
  notes: `Krishna Chaitanya. The five prompt-optimization techniques, all live. The two BLUE cards own history (summarization compresses, pruning selects) - they each get their own section, and only one of them can own history at a time. The three TURMERIC ones wrap the model call and compose with everything. Shared stance: every removal is deterministic and local - keyword match, exact-hash match, hand-tightened rewrite - never an LLM call to save tokens, never an estimated saving.`,
});

Deck.add({
  id: "pc-concept",
  hud: true,
  tokens: 6150,
  cost: 0.0360,
  html: `
    <div class="slide-head">
      <div class="kicker">02 &middot; Prompt caching</div>
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
  notes: `The meter here shows the target economics of a cache hit - be explicit that the dollar figure depends on a provider actually billing the cached prefix at a discount. What's real today, measured on the next slide: the byte-stable prefix construction that makes a cache hit possible at all. Point: caching doesn't cut tokens, it cuts the PRICE of the repeated ones - so the token gauge barely moves while cost growth flattens.`,
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
        <div class="cap">Send fewer tokens</div>
        <div class="body">The five techniques &mdash; pruning, summarization, tool filtering, compression, deduplication &mdash; each remove a different kind of waste. <b>Live</b>, each behind its own flag, all measured in the notebook.</div>
      </div>
      <div class="tw-card wave">
        <div class="cap">Cache the stable prefix</div>
        <div class="body">A <code>ProviderCacheAdapter</code> seam sits at the API boundary, ready for a vendor-specific cache hint &mdash; the default passes requests through unchanged.</div>
      </div>
    </div>
    <div class="callout" style="margin-top:20px;">
      Already live: <b>cache-friendly prompt construction</b> (next) builds the byte-stable prefix a cache can actually reuse &mdash; the part every provider's cache needs before it can do anything.
    </div>
  `,
  notes: `Reassure the room this isn't special-cased: it's the same plug-in pattern every optimization uses. The three new techniques (tool filtering, compression, deduplication) all wrap the model call via a decorator; the two history ones plug in as a history policy. The deterministic construction caching depends on is implemented and measured - next section - the vendor-specific cache_control hint is a seam waiting for the first provider that needs it.`,
});

Deck.add({
  id: "pc-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Measure it: baseline vs. cache-friendly</h2>
      <p class="lead" style="max-width:44ch;">Run the same task twice &mdash; once plain, once with the flag &mdash; and compare the stable-prefix hash and reuse ratio.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Optimization 2 &mdash; Prompt optimization &amp; caching&rdquo;</div>
          <div class="s">Run <code>opt_cache["session"].cache_report()</code> to see the prefix hash, size, and reuse across turns.</div>
        </div>
        <div class="nb-cmd">${TW.techFlag('prompt-caching')}</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">Expect: a byte-identical stable prefix every turn, real input tokens read from provider usage &mdash; never estimated.</p>
    </div>
  `,
  notes: `Everyone runs it. The deliverable is /cache's stable-prefix hash staying identical turn to turn - that's the proof the prefix is actually reusable, not just "probably fine". Hand over to the dedicated cache-friendly-prompts section for the full walkthrough.`,
});
