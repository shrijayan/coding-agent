/* ================================================= 60 · AGENT LOOP PREVENTION
   Technique #5 - LIVE in the repo. Agents get stuck: same failing tool call on
   repeat, burning tokens and money. Detect the loop and break it. The
   concept demo keeps fragments + HUD; the plan slide is static.
============================================================================ */

Deck.add({
  id: "lp-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:${TW.techAccent('loop-prevention')};">
      <div class="bar"></div>
      <div class="idx">${TW.techIdx('loop-prevention')}</div>
      <h1>${TW.techTitle('loop-prevention')}</h1>
      <p>A stuck agent is the most expensive agent: it repeats the same failing move and bills you for every lap.</p>
      ${TW.techMeta('loop-prevention')}
    </div>
  `,
  notes: `Adithya. Not a token-per-turn saving - a catastrophe cap. When an agent loops, cost climbs with zero progress. This detects it and stops the bleed.`,
});

Deck.add({
  id: "lp-concept",
  hud: true,
  tokens: 5200,
  cost: 0.0300,
  html: `
    <div class="slide-head">
      <div class="kicker">05 &middot; Agent loop prevention</div>
      <h2>Spot the lap, stop the spend</h2>
    </div>
    <div class="split top" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.82em;font-family:var(--tw-mono);">
          <div style="padding:12px 16px;border-radius:10px;background:var(--tw-mist);">edit_file config.py &rarr; error</div>
          <div style="padding:12px 16px;border-radius:10px;background:var(--tw-mist);">edit_file config.py &rarr; error</div>
          <div class="fragment fade-in" data-fragment-index="0" style="padding:12px 16px;border-radius:10px;background:var(--tint-flamingo);color:#b03a51;" data-cost="0.0420" data-tokens="7600" data-hint="same call, no progress, cost rising">edit_file config.py &rarr; error &nbsp;<b>(3&times;!)</b></div>
          <div class="fragment fade-in" data-fragment-index="1" style="padding:12px 16px;border-radius:10px;background:var(--tint-turmeric);color:#8a5a06;" data-cost="0.0455" data-tokens="9100" data-hint="unchecked: cost runs away">edit_file config.py &rarr; error &nbsp;<b>(4&times;!)</b></div>
        </div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="fragment fade-in callout" data-fragment-index="2" style="border-left-color:var(--tw-jade);"
               data-cost="0.0455" data-tokens="1400" data-hint="loop broken - spend capped">
            <b>Guard trips.</b> Identical call + no state change &rarr; break the loop, drop the dead context, re-plan or stop cleanly.
          </div>
          <div class="fragment fade-in" data-fragment-index="3">
            <div class="icon-rows">
              <div class="icon-row flamingo"><div class="ic">${TW.icon('loop')}</div><div class="tx"><b>Detect</b> &mdash; repeated calls, no progress, cost caps.</div></div>
              <div class="icon-row jade"><div class="ic">${TW.icon('shield')}</div><div class="tx"><b>Recover</b> &mdash; nudge a new strategy, or halt cleanly.</div></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  notes: `Step it: the same failing edit repeats, cost climbs, tokens climb - then the guard trips, freezes the spend and clears the dead loop. The repo also has AGENT_MAX_ITERATIONS and the CostGuard soft cap as blunt backstops; loop-guard is the layer above them that detects the loop by repetition/no-progress and recovers, instead of just hitting a ceiling. In the notebook, a cooperative prompt set correctly triggers zero nudges and zero halts - only a prompt built to loop (an intentionally broken shell command) trips the guard for real.`,
});

Deck.add({
  id: "lp-plan",
  html: `
    <div class="slide-head">
      <div class="kicker">05 &middot; How it layers with the existing caps</div>
      <h2>From blunt caps to real detection</h2>
    </div>
    <div class="card-grid cols-3" style="margin-top:20px;">
      <div class="tw-card wave"><div class="cap">Iteration cap</div><div class="body">A hard lap ceiling in the loop. Safe, but dumb &mdash; it can't tell progress from spinning.</div></div>
      <div class="tw-card turmeric"><div class="cap">Cost guard</div><div class="body">A soft per-session spend cap. Stops before the shared budget burns.</div></div>
      <div class="tw-card flamingo"><div class="cap">Loop detector</div><div class="body">Spots the same failing call repeating, nudges once, then halts cleanly with zero further API calls. <b>Live.</b></div></div>
    </div>
    <div class="callout" style="margin-top:20px;">The caps are the safety net. The detector is the fix &mdash; it catches the loop early, well before either cap is reached.</div>
  `,
  notes: `Adithya. Frame it as maturity: caps already protect the budget (max iterations + cost guard). loop-guard detects the loop by behaviour and intervenes, so you rarely hit the caps at all.`,
});

Deck.add({
  id: "lp-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Measure it: cooperative vs. stuck</h2>
      <p class="lead" style="max-width:44ch;">Run a normal task first, then a prompt built to loop &mdash; and watch the guard trip only when it's real.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Optimization 4 &mdash; Agent loop prevention&rdquo;</div>
          <div class="s">Run <code>opt_loop_guard["session"].loop_guard_report()</code>, then the stress-prompt cell to force a real halt.</div>
        </div>
        <div class="nb-cmd">${TW.techFlag('loop-prevention')}</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">Expect: zero nudges/halts on the cooperative demo prompts, and a real nudge-then-halt on the stress prompt &mdash; with a true-zero cost for the halted call.</p>
    </div>
  `,
  notes: `Everyone runs it. The honesty point: we don't fake a loop on the main demo set to make the chart look good - zero is the correct result there. The stress-prompt cell is a deliberately broken shell command that shows the guard actually tripping.`,
});
