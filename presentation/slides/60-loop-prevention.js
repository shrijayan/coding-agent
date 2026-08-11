/* ================================================= 60 · AGENT LOOP PREVENTION
   Technique #5 - IN PROGRESS. Agents get stuck: same failing tool call on
   repeat, burning tokens and money. Detect the loop and break it. The
   concept demo keeps fragments + HUD; the plan slide is static.
============================================================================ */

Deck.add({
  id: "lp-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:var(--tw-flamingo);">
      <div class="bar"></div>
      <div class="idx">Technique 05</div>
      <h1>Agent loop prevention</h1>
      <p>A stuck agent is the most expensive agent: it repeats the same failing move and bills you for every lap.</p>
      <div class="sep-meta">
        <span class="pill wip"><span class="dot"></span>in progress</span>
        <div class="flag">detect &middot; break &middot; recover</div>
      </div>
    </div>
  `,
  notes: `Presenter Three. Not a token-per-turn saving - a catastrophe cap. When an agent loops, cost climbs with zero progress. This detects it and stops the bleed.`,
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
  notes: `Design slide. Step it: the same failing edit repeats, cost climbs, tokens climb - then the guard trips, freezes the spend and clears the dead loop. Today the repo has AGENT_MAX_ITERATIONS and the CostGuard soft cap as blunt backstops; the new piece is detecting the loop by repetition/no-progress and recovering, not just hitting a ceiling.`,
});

Deck.add({
  id: "lp-plan",
  html: `
    <div class="slide-head">
      <div class="kicker">05 &middot; What exists, what's new</div>
      <h2>From blunt caps to real detection</h2>
    </div>
    <div class="card-grid cols-3" style="margin-top:20px;">
      <div class="tw-card wave"><div class="cap">Today: iteration cap</div><div class="body">A hard lap ceiling in the loop. Safe, but dumb &mdash; it can't tell progress from spinning.</div></div>
      <div class="tw-card turmeric"><div class="cap">Today: cost guard</div><div class="body">A soft per-session spend cap. Stops before the shared budget burns.</div></div>
      <div class="tw-card flamingo"><div class="cap">New: loop detector</div><div class="body">Spots repeated calls with no progress, breaks the loop, and re-plans. <b>Building now.</b></div></div>
    </div>
    <div class="callout" style="margin-top:20px;">The caps are the safety net. The detector is the fix &mdash; catch the loop early, before either cap is even reached.</div>
  `,
  notes: `Presenter Three. Frame it as maturity: caps already protect the budget (max iterations + cost guard). The optimization is detecting the loop by behaviour and intervening, so you rarely hit the caps at all.`,
});
