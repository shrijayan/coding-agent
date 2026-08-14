/* ==================================================== 50 · CONTEXT PRUNING
   Technique #4a - LIVE in the repo. One half of context_window.py: once a
   tool result falls outside the recent-message window and is bulky, replace
   it with a short placeholder instead of resending it forever. Always on
   when context-window is enabled (the other half, skills-on-demand, is its
   own technique - 55-context-skills.js). The notebook proves this under the
   shipped DEFAULT thresholds with a seeded "legacy" file fixture, and
   ablates skills on/off to isolate prune-only from prune+skills.
============================================================================ */

Deck.add({
  id: "cw-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:${TW.techAccent('context-pruning')};">
      <div class="bar"></div>
      <div class="idx">${TW.techIdx('context-pruning')}</div>
      <h1>${TW.techTitle('context-pruning')}</h1>
      <p>Summarization compresses the past. This is about <em>relevance</em> &mdash; drop what this step doesn't need, keep everything else untouched.</p>
      ${TW.techMeta('context-pruning')}
    </div>
  `,
  notes: `Adithya. The trap: a single 900-line file dump or a stale tool output rides along in every future call. Context pruning drops it by relevance so the window stays small and sharp.`,
});

Deck.add({
  id: "cw-concept",
  hud: true,
  tokens: 9800,
  cost: 0.0400,
  html: `
    <div class="slide-head">
      <div class="kicker">04a &middot; Context pruning</div>
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
            <b>Prune by relevance.</b> Once a tool result falls outside the recent-message window and is bulky, replace it with a short, specific placeholder &mdash; never a vague "something was removed."
          </div>
          <div class="fragment fade-in" data-fragment-index="1">
            <div class="bignum"><div class="n">~57%<span class="unit"> smaller</span></div><div class="lbl">context reduction, once there's actually something bulky to prune</div></div>
          </div>
          <div class="fragment fade-in callout" data-fragment-index="2" style="border-left-color:var(--tw-sapphire);">
            The chars-removed figure is a <b>deterministic fact</b> about the dropped text &mdash; never an estimate, same rule cache-friendly's byte figures follow.
          </div>
        </div>
      </div>
    </div>
  `,
  notes: `Contrast clearly with summarization: summarization = compress old turns to prose; pruning = SELECT relevant items and drop the rest, replacing bulky stale output with a placeholder. Honesty note: the notebook proves this two ways - a small demo with thresholds deliberately tuned down (so the tiny calculator task has anything to prune at all), and a bigger seeded-file demo that needs no tuning under the shipped defaults. Use the second one if anyone asks "is that number real or did you rig the thresholds?"`,
});

Deck.add({
  id: "cw-plan",
  html: `
    <div class="slide-head">
      <div class="kicker">04a &middot; Where it plugs in</div>
      <h2>Same hook as summarization &mdash; with a catch</h2>
    </div>
    <div class="card-grid cols-2" style="margin-top:20px;">
      <div class="tw-card wave"><div class="cap">It decides what gets sent</div><div class="body">Same plug-in point summarization uses (<code>history_policy</code>). Here it <b>filters by relevance</b> instead of compressing into prose.</div></div>
      <div class="tw-card flamingo"><div class="cap">Only one policy can own history</div><div class="body">Two optimizations both setting <code>history_policy</code> <b>refuses to start</b> &mdash; so prune vs. summarize is a real choice, never last-writer-wins.</div></div>
    </div>
    <div class="callout" style="margin-top:20px;">
      That's a deliberate constraint, not a gap: <b>compress</b> and <b>prune</b> stay two distinct, single-owner policies rather than silently stacking. It doesn't touch the other half of this technique, though &mdash; skills-on-demand (next) composes freely with either one.
    </div>
  `,
  notes: `Adithya. Honest engineering note straight from the repo: history_policy has a single owner by design (ConflictingOptimizationsError) - so pruning + summarization can't both just be switched on at once. Sets up the contrast with skills-on-demand, next: that half is extra_tools/system_prompt_suffix, which concatenate across optimizations (bundle.py's merged_with) - never in this fight.`,
});

Deck.add({
  id: "cw-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Measure it: prune it for real</h2>
      <p class="lead" style="max-width:46ch;">Skip the plain demo-prompts run for this one &mdash; use the dedicated pruning demo, which seeds a real &ldquo;legacy&rdquo; file first so there's something bulky to drop.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Optimization 5 &mdash; Context window optimization&rdquo;</div>
          <div class="s">Run <code>seed_legacy_file</code>, then compare <code>opt_context2</code> (prune+skills) vs. <code>opt_context_pruning_only</code> (<code>AGENT_CONTEXT_WINDOW_SKILLS_ENABLED=false</code>) to see pruning in isolation, under the shipped default thresholds.</div>
        </div>
        <div class="nb-cmd">${TW.techFlag('context-pruning')}</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">Expect: a measured chars-pruned count once there's something bulky and stale to drop, isolated cleanly from skills either way &mdash; no tuned thresholds needed.</p>
    </div>
  `,
  notes: `Everyone runs it. Watch the pruning ablation's comparison table - prune-only vs. prune+skills should show close but not identical savings, since the skills menu (next technique) adds its own small system-prompt-suffix cost even when unused. If someone insists on running the plain DEMO_PROMPTS opt_context instead, flag that it needs its thresholds tuned down first (keep_recent=3, min_chars=150) to have anything to prune at all - the seeded-file demo needs no such tuning.`,
});
