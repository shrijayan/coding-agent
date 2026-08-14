/* ============================================ 30 · PROMPT OPTIMIZATION & CACHING
   Technique #2 - LIVE in the repo. Two levers: (a) prompt optimization - a
   family of FOUR techniques, all live (context pruning, summarization, tool
   filtering, prompt compression); (b) prompt caching -
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
  notes: `Krishna Chaitanya. Two levers here: (1) prompt optimization - not one trick but a FAMILY OF FOUR techniques, all live in the repo: context pruning (context-window), conversation summarization (conversation-summary), tool filtering, prompt compression; (2) prompt caching - providers bill a cached prefix at ~10%. What's live today on the caching side: the deterministic, byte-stable prefix construction (cache-friendly-prompts, next section) that any provider cache needs before it can reuse anything - plus the ProviderCacheAdapter seam a vendor-specific cache hint drops into.`,
});

Deck.add({
  id: "pc-family",
  html: `
    <div class="slide-head">
      <div class="kicker">02 &middot; Prompt optimization</div>
      <h2>Not one trick &mdash; four techniques</h2>
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
      <div class="tw-card wave">
        <div class="cap">All four compose</div>
        <div class="body">Every removal is deterministic and local &mdash; never a model call that spends tokens to save tokens, never an estimate.</div>
      </div>
    </div>
  `,
  notes: `Krishna Chaitanya. The four prompt-optimization techniques, all live. The two BLUE cards own history (summarization compresses, pruning selects) - they each get their own section, and only one of them can own history at a time. The two TURMERIC ones wrap the model call and compose with everything. Shared stance: every removal is deterministic and local - keyword match, hand-tightened rewrite - never an LLM call to save tokens, never an estimated saving.`,
});

Deck.add({
  id: "pc-optmap",
  html: `
    <div class="slide-head">
      <div class="kicker">02 &middot; Prompt optimization</div>
      <h2>Which technique trims which layer</h2>
    </div>
    <div class="optmap" id="optmap">
      <div class="row sys">
        <div class="layer"><b>System prompt</b></div>
        <div class="tech fragment fade-in" data-fragment-index="0">
          <span class="chip compress">Prompt compression</span>
          <span class="note">rewrite long instructions into shorter equivalents &mdash; same meaning, fewer tokens</span>
        </div>
      </div>
      <div class="row tools">
        <div class="layer"><b>Tool definitions</b></div>
        <div class="tech fragment fade-in" data-fragment-index="1">
          <span class="chip filter">Tool filtering</span>
          <span class="chip compress">+ compression</span>
          <span class="note">expose only the tools this request needs &mdash; and describe them tersely</span>
        </div>
      </div>
      <div class="row hist">
        <div class="layer"><b>Conversation history</b></div>
        <div class="tech fragment fade-in" data-fragment-index="2">
          <span class="chip prune">Context pruning</span>
          <span class="chip summary">+ summarization</span>
          <span class="note">drop stale tool output; fold old turns into a running summary</span>
        </div>
      </div>
      <div class="row new">
        <div class="layer"><b>New message</b></div>
        <div class="tech fragment fade-in" data-fragment-index="3">
          <span class="chip none">Always fresh</span>
          <span class="note">the churn &mdash; nothing to trim, it changes every single turn</span>
        </div>
      </div>
    </div>
  `,
  notes: `Krishna Chaitanya. The four prompt-optimization techniques aren't a grab-bag - each targets a different LAYER of the request. Click through one layer at a time: (1) the SYSTEM PROMPT is fixed text we author, so prompt compression rewrites it shorter; (2) TOOL DEFINITIONS get filtered to just what the request needs, then compacted; (3) CONVERSATION HISTORY is where the tokens really pile up - prune stale tool output and summarize old turns; (4) the NEW MESSAGE is the only genuinely fresh part, so there's nothing to trim there. Land it: caching (coming after cache-friendly prompts) is the complementary lever - it makes the tokens that MUST repeat cheaper, rather than fewer.`,
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
