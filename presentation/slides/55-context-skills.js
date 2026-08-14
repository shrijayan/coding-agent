/* ================================================= 55 · SKILLS, LOADED ON DEMAND
   Technique #5b - LIVE in the repo. The other half of context_window.py:
   the system prompt carries only a short menu (name + one-line
   description) for each skill; the full guidance only enters context when
   the model actually calls load_skill(name). Independently gated by its own
   env var (AGENT_CONTEXT_WINDOW_SKILLS_ENABLED, default true) - can be
   switched off while pruning (5a) stays on. Composes with ANY optimization
   (extra_tools + system_prompt_suffix), unlike pruning, which is locked to
   history_policy's single-owner rule.
============================================================================ */

Deck.add({
  id: "cs-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:${TW.techAccent('context-skills')};">
      <div class="bar"></div>
      <div class="idx">${TW.techIdx('context-skills')}</div>
      <h1>${TW.techTitle('context-skills')}</h1>
      <p>Reference material the model needs occasionally shouldn't ride along on every request the way a static system-prompt block would.</p>
      ${TW.techMeta('context-skills')}
    </div>
  `,
  notes: `Adithya. Different kind of "context window" problem from pruning: not stale history to drop, but reference material (how we like tests written, commit style, ...) that's only relevant sometimes. Carrying it always would cost tokens on every single call, used or not.`,
});

Deck.add({
  id: "cs-concept",
  hud: true,
  tokens: 6400,
  cost: 0.0210,
  html: `
    <div class="slide-head">
      <div class="kicker">05b &middot; Skills, loaded on demand</div>
      <h2>Pay for the menu, not the whole shelf</h2>
    </div>
    <div class="split top" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.85em;">
          <div style="display:flex;justify-content:space-between;gap:12px;padding:13px 17px;border-radius:10px;background:var(--tw-mist);"><span><b>System prompt</b> carries just this:</span></div>
          <div style="padding:13px 17px;border-radius:10px;background:var(--tint-jade);font-family:var(--tw-mono);font-size:0.78em;line-height:1.6;">
            - docstring-style: how to write docstrings&hellip;<br>
            - git-commit-style: how to write a commit message&hellip;<br>
            - pytest-conventions: how to write pytest tests&hellip;
          </div>
          <div class="fragment fade-in" data-fragment-index="0" style="padding:13px 17px;border-radius:10px;background:var(--tw-mist);"><span>Model calls <code>load_skill("pytest-conventions")</code>&hellip;</span></div>
          <div class="fragment fade-in" data-fragment-index="0" style="padding:13px 17px;border-radius:10px;background:var(--tint-flamingo);font-size:0.82em;">&hellip;only <b>that one skill's</b> full body enters context, right now, not before.</div>
        </div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="fragment fade-in callout" data-fragment-index="1" style="border-left-color:var(--tw-jade);">
            <b>Menu, not the manual.</b> Every skill's name + one-line description is always present; the full guidance is not.
          </div>
          <div class="fragment fade-in" data-fragment-index="2">
            <div class="bignum"><div class="n">~84%<span class="unit"> smaller</span></div><div class="lbl">this repo's skills menu vs. all three skills' full bodies, measured in bytes</div></div>
          </div>
          <div class="fragment fade-in callout" data-fragment-index="3" style="border-left-color:var(--tw-turmeric);">
            Independently gated: <code>AGENT_CONTEXT_WINDOW_SKILLS_ENABLED</code> can turn this off while pruning (4a) stays on.
          </div>
        </div>
      </div>
    </div>
  `,
  notes: `The ~84% figure is a real, deterministic measurement of this repo's skills/ directory (menu chars vs. total body chars across the 3 shipped skills) - not a guess, recomputable any time the skills change. Step it: menu is always there (cheap); a skill's body only shows up in context the turn the model actually decides it's relevant and calls load_skill. That's the "on demand" claim, literally.`,
});

Deck.add({
  id: "cs-how",
  html: `
    <div class="slide-head">
      <div class="kicker">05b &middot; Where it plugs in</div>
      <h2>A tool, not a history policy</h2>
    </div>
    <div class="card-grid cols-2" style="margin-top:20px;">
      <div class="tw-card sapphire"><div class="cap">Just a tool + a menu</div><div class="body">Registered via <code>extra_tools</code> (<code>load_skill</code>) and a short <code>system_prompt_suffix</code> &mdash; the same two seams any optimization can use.</div></div>
      <div class="tw-card wave"><div class="cap">Composes with anything</div><div class="body"><code>extra_tools</code> and <code>system_prompt_suffix</code> concatenate across optimizations (<code>bundle.py</code>'s <code>merged_with</code>) &mdash; never a single-owner fight, unlike <code>history_policy</code>.</div></div>
    </div>
    <div class="callout" style="margin-top:20px;">
      That's the real contrast with pruning (4a): pruning has to fight for the one <code>history_policy</code> seat; skills-on-demand never has to fight for anything.
    </div>
  `,
  notes: `Adithya. Skills are deliberately built on the two additive extension points, not the single-owner one. So context-window's skills half stacks with conversation-summary, hybrid-routing, loop-guard - anything - with zero coordination needed. Pruning can't make that claim, which is the point of splitting these into two techniques instead of one.`,
});

Deck.add({
  id: "cs-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Measure it: watch a skill load, live</h2>
      <p class="lead" style="max-width:46ch;">Run the task set that includes a test-writing prompt, and watch for the exact turn a skill's full guidance shows up.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Optimization 5 &mdash; Context window optimization&rdquo;</div>
          <div class="s">Run <code>opt_context["session"].context_report()</code> and watch the <code>[tool]</code> lines for a <code>load_skill</code> call on the test-writing turn.</div>
        </div>
        <div class="nb-cmd">${TW.techFlag('context-skills')}</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">Expect: <code>load_skill("pytest-conventions")</code> fires exactly once, right when the model starts writing tests &mdash; not before, not for the other skills it never needed.</p>
    </div>
  `,
  notes: `Everyone runs it. This is a different notebook cell from 4a's pruning demo - the pruning ablation's prompt set never asks the model to write tests, so it never triggers load_skill at all. This is the run where skills-on-demand fires for real, not just described. Compare against the pruning-only ablation's tiny skills-menu overhead (4a's notebook slide) to see the full picture: near-zero cost when unused, real value when used.`,
});
