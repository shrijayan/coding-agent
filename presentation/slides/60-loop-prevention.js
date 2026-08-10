/* ================================================= 60 · AGENT LOOP PREVENTION
   Technique #5 - IN PROGRESS. Agents get stuck: same failing tool call on
   repeat, oscillating edits, no progress - burning tokens and money. Detect
   the loop and break it. The repo already ships two blunt guards
   (AGENT_MAX_ITERATIONS + CostGuard); the smarter detector is what's new.
============================================================================ */

Deck.add({
  id: "lp-sep",
  hideHud: true,
  html: `
    <div class="separator">
      <div class="txt">
        <div class="idx">Technique 05</div>
        <h1>Agent loop<br/>prevention</h1>
        <p>A stuck agent is the most expensive agent: it repeats the same failing move and bills you for every lap.</p>
        <div style="margin-top:18px;"><span class="pill wip"><span class="dot"></span>in progress</span></div>
      </div>
      <div class="visual teal">
        <div style="text-align:center;color:#eaf4f6;">
          <div style="font-size:3em;color:#ff8ea1;">${TW.icon('loop')}</div>
          <div style="font-family:var(--tw-mono);font-size:0.72em;margin-top:12px;color:#9fb6bd;">detect &middot; break &middot; recover</div>
        </div>
      </div>
    </div>
  `,
  notes: `Presenter Three. Not a token-per-turn saving - a catastrophe cap. When an agent loops, cost climbs with zero progress. This detects it and stops the bleed.`,
});

Deck.add({
  id: "lp-concept",
  hideHud: false,
  tokens: 5200,
  cost: 0.0300,
  html: `
    <div class="slide-head">
      <div class="kicker">05 &middot; Agent loop prevention</div>
      <h2>Spot the lap, stop the spend</h2>
    </div>
    <div class="split top" style="grid-template-columns:1fr 1fr;">
      <div class="col">
        <div class="stack-sm" style="font-size:0.78em;font-family:var(--tw-mono);">
          <div style="padding:9px 12px;border-radius:8px;background:var(--tw-card);">edit_file config.py &rarr; error</div>
          <div style="padding:9px 12px;border-radius:8px;background:var(--tw-card);">edit_file config.py &rarr; error</div>
          <div class="fragment fade-in" data-fragment-index="0" style="padding:9px 12px;border-radius:8px;background:#fdeef1;color:var(--tw-coral-600);" data-cost="0.0420" data-tokens="7600" data-hint="same call, no progress, cost rising">edit_file config.py &rarr; error &nbsp;<b>(3&times;!)</b></div>
          <div class="fragment fade-in" data-fragment-index="1" style="padding:9px 12px;border-radius:8px;background:#fff6e6;color:#9a6a00;" data-cost="0.0455" data-tokens="9100" data-hint="unchecked: cost runs away">edit_file config.py &rarr; error &nbsp;<b>(4&times;!)</b></div>
        </div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="fragment fade-in callout" data-fragment-index="2" style="border-left-color:var(--tw-green);"
               data-cost="0.0455" data-tokens="1400" data-hint="loop broken - spend capped">
            <b>Guard trips.</b> Identical call + no state change &rarr; break the loop, drop the dead context, and either re-plan or stop cleanly.
          </div>
          <div class="fragment fade-in" data-fragment-index="3">
            <div class="icon-rows" style="font-size:0.92em;">
              <div class="icon-row coral"><div class="ic">${TW.icon('loop')}</div><div class="tx"><b>Detect</b> &mdash; repeated tool calls / no diff / iteration + cost caps.</div></div>
              <div class="icon-row green"><div class="ic">${TW.icon('shield')}</div><div class="tx"><b>Recover</b> &mdash; nudge with a new strategy, or halt before the budget burns.</div></div>
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
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">What already exists &middot; what's new</div>
      <h2>From blunt caps to real detection</h2>
    </div>
    <div class="card-grid cols-3">
      <div class="tw-card teal"><div class="cap">Today: AGENT_MAX_ITERATIONS</div><div class="body">A hard lap ceiling in the loop. Safe, but dumb &mdash; it can't tell progress from spinning.</div></div>
      <div class="tw-card amber"><div class="cap">Today: CostGuard</div><div class="body">Soft per-session $ cap (<code>session_cost_cap_usd</code>). Stops before the shared budget burns.</div></div>
      <div class="tw-card coral"><div class="cap">New: loop detector</div><div class="body">Repeated-call / no-progress detection that breaks and re-plans &mdash; a <code>wrap_llm_client</code> guard. <b>Building now.</b></div></div>
    </div>
    <div class="callout" style="margin-top:16px;">The caps are the safety net. The detector is the fix &mdash; catch the loop early, before either cap is even reached.</div>
  `,
  notes: `Presenter Three. Frame it as maturity: caps already protect the budget (max iterations + cost guard). The optimization is detecting the loop by behaviour and intervening, so you rarely hit the caps at all.`,
});
