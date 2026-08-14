/* ============================================== 20 · CONVERSATION SUMMARIZATION
   Technique #1 - LIVE in the repo. The concept slide (when it pays off +
   which kind to use), then the centrepiece animation: history collapses
   into a running summary, tokens drop while cost ticks up for the
   summarize call. This is an OPTIMIZATION SHOWCASE, so it keeps its
   step-by-step fragments and the HUD.
============================================================================ */

Deck.add({
  id: "sum-sep",
  dark: true,
  html: `
    <div class="separator" style="--sep-accent:${TW.techAccent('summarization')};">
      <div class="bar"></div>
      <div class="idx">${TW.techIdx('summarization')}</div>
      <h1>${TW.techTitle('summarization')}</h1>
      <p>Every turn re-sends the whole transcript &mdash; and it only grows. So stop re-sending all of it.</p>
      ${TW.techMeta('summarization')}
    </div>
  `,
  notes: `Shrijayan. The problem in one line: every turn re-sends the whole transcript, and the transcript only grows. Summarization caps that.`,
});

Deck.add({
  id: "sum-concept",
  html: `
    <div class="slide-head">
      <div class="kicker">01 &middot; Conversation summarization</div>
      <h2>When it pays off &mdash; and which kind to use</h2>
    </div>
    <div class="split top" style="grid-template-columns:0.92fr 1.08fr;align-items:stretch;">
      <div class="col" style="display:flex;flex-direction:column;gap:12px;">
        <div style="flex:1;border-radius:8px;background:var(--tint-jade);padding:14px 18px;">
          <div style="display:flex;align-items:center;gap:8px;font-weight:800;color:var(--tw-ink);margin-bottom:8px;"><span style="color:var(--tw-jade);font-size:1.05em;">${TW.icon('check')}</span>Use it when&hellip;</div>
          <div style="font-size:0.78em;color:var(--tw-ink-soft);line-height:1.5;">
            <div style="margin-bottom:6px;"><b>Long sessions</b> &mdash; 20+ turns in, the transcript dominates every call.</div>
            <div style="margin-bottom:6px;"><b>Old turns are stale anyway</b> &mdash; the plot matters, not the exact words.</div>
            <div><b>Cost-sensitive</b> &mdash; every call is billed per token, and history only grows.</div>
          </div>
        </div>
        <div style="flex:1;border-radius:8px;background:var(--tint-flamingo);padding:14px 18px;">
          <div style="display:flex;align-items:center;gap:8px;font-weight:800;color:var(--tw-ink);margin-bottom:8px;"><span style="color:var(--tw-flamingo);font-size:1.05em;">${TW.icon('scissors')}</span>Skip it when&hellip;</div>
          <div style="font-size:0.78em;color:var(--tw-ink-soft);line-height:1.5;">
            <div style="margin-bottom:6px;"><b>Short tasks</b> &mdash; the summarizer call itself can cost more than it saves.</div>
            <div><b>Verbatim details still needed</b> &mdash; a summary is lossy. That's <b>context-window's</b> job: prune &amp; re-fetch on demand.</div>
          </div>
        </div>
      </div>
      <div class="col" style="display:flex;flex-direction:column;gap:10px;">
        <div style="display:flex;gap:12px;align-items:center;padding:11px 16px;border-radius:8px;background:var(--tw-mist);">
          <span style="font-size:1.15em;color:var(--tw-sapphire);flex:none;">${TW.icon('summarize')}</span>
          <div style="min-width:0;">
            <div style="font-family:var(--tw-mono);font-weight:700;font-size:0.76em;color:var(--tw-ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Running summary &nbsp;${TW.pill('live')}</div>
            <div style="font-size:0.76em;color:var(--tw-ink-soft);line-height:1.35;">Old turns fold into a cached summary; recent ones stay verbatim.</div>
            <div style="font-size:0.7em;color:var(--tw-muted);margin-top:3px;"><b>Use for:</b> one long evolving task</div>
          </div>
        </div>
        <div style="display:flex;gap:12px;align-items:center;padding:11px 16px;border-radius:8px;background:var(--tw-mist);">
          <span style="font-size:1.15em;color:var(--tw-muted);flex:none;">${TW.icon('stack')}</span>
          <div style="min-width:0;">
            <div style="font-family:var(--tw-mono);font-weight:700;font-size:0.76em;color:var(--tw-ink);">One-shot re-summarize</div>
            <div style="font-size:0.76em;color:var(--tw-ink-soft);line-height:1.35;">Whole transcript re-summarized from scratch &mdash; simple, but the cost grows with history. Why we don't.</div>
            <div style="font-size:0.7em;color:var(--tw-muted);margin-top:3px;"><b>Use for:</b> quick handoffs</div>
          </div>
        </div>
        <div style="display:flex;gap:12px;align-items:center;padding:11px 16px;border-radius:8px;background:var(--tw-mist);">
          <span style="font-size:1.15em;color:var(--tw-muted);flex:none;">${TW.icon('context')}</span>
          <div style="min-width:0;">
            <div style="font-family:var(--tw-mono);font-weight:700;font-size:0.76em;color:var(--tw-ink);">Query-based</div>
            <div style="font-size:0.76em;color:var(--tw-ink-soft);line-height:1.35;">Only the parts that answer the current question get summarized.</div>
            <div style="font-size:0.7em;color:var(--tw-muted);margin-top:3px;"><b>Use for:</b> mixed-topic sessions</div>
          </div>
        </div>
        <p class="muted" style="font-size:0.72em;margin-top:2px;">Bulky tool output? This agent <b>prunes</b> it instead &mdash; that's context-window's job.</p>
      </div>
    </div>
  `,
  notes: `Shrijayan. Two halves, one message each. LEFT: the decision rule - summarization wins on long sessions where old turns are stale; it loses on short tasks (the summarize call is real money) and whenever verbatim detail still matters (that's context-window territory - sets up technique 04). RIGHT: the menu - this agent implements exactly ONE kind, the running summary: fold only what's new into a cached summary, recent stays verbatim. The other two exist in the wild but deliberately not here: one-shot re-summarization grows unbounded, query-based needs a retrieval layer.`,
});

Deck.add({
  id: "sum-lab",
  hud: true,
  tokens: 12400,
  cost: 0.0182,
  html: `
    <div class="slide-head">
      <div class="kicker">01 &middot; Conversation summarization</div>
      <h2>Compress the past, keep the plot</h2>
    </div>

    <div class="sumlab" id="sumlab" data-state-initial="1">
      <div class="lane">
        <div class="lane-title">What we send the model <span class="badge">next call</span></div>
        <div class="stream">
          <div class="summary-card">
            <span class="tag">Running summary</span>
            User is refactoring auth: created <b>auth.py</b>, edited <b>login.py</b>, tests pass. Still open: the logout route.
          </div>
          <div class="msg user old"><span class="who">user</span>Refactor the auth module for clarity.</div>
          <div class="msg asst old"><span class="who">assistant</span>Reading auth.py and login.py&hellip;</div>
          <div class="msg tool old">read_file auth.py &rarr; 240 lines</div>
          <div class="msg asst old"><span class="who">assistant</span>Extracting a helper, editing login.py&hellip;</div>
          <div class="msg tool old">edit_file login.py &rarr; ok</div>
          <div class="msg tool old">bash pytest &rarr; 3 passed</div>
          <div class="msg user"><span class="who">user</span>Now add a logout endpoint.</div>
          <div class="msg asst"><span class="who">assistant</span>Sure &mdash; point me at the router.</div>
        </div>
      </div>

      <div class="side">
        <div class="summarizer">
          <span class="em">${TW.icon('summarize')}</span>
          <span class="lb"><b>Summarizer</b>one extra model call</span>
        </div>
        <div class="ba">
          <div class="row before"><span class="lab">before</span><span class="v">12,400 tok</span></div>
          <div class="row cost"><span class="lab">summarize</span><span class="v">+$0.0045</span></div>
          <div class="row after"><span class="lab">after</span><span class="v">3,200 tok</span></div>
        </div>
      </div>
    </div>

    <div class="stepline" style="margin-top:14px;font-size:0.9em;color:var(--tw-ink-soft);">
      <span class="fragment current-visible" data-fragment-index="0"
            data-set-state="1" data-state-el="#sumlab" data-tokens="12400" data-cost="0.0182"
            data-hint="history is re-sent every single turn">
        Every turn re-sends the <b>entire</b> transcript. &#8599; watch the meter.
      </span>
      <span class="fragment current-visible" data-fragment-index="1"
            data-set-state="2" data-state-el="#sumlab" data-tokens="12400" data-cost="0.0227"
            data-hint="summarizer call = +$0.0045 once">
        Past a threshold, fold old messages into one summary &mdash; itself a real, <b>paid</b> call.
      </span>
      <span class="fragment current-visible" data-fragment-index="2"
            data-set-state="3" data-state-el="#sumlab" data-tokens="3200" data-cost="0.0227"
            data-hint="context shrinks ~74%">
        Old turns collapse into the summary; recent ones stay verbatim. <b>Tokens drop 74%.</b>
      </span>
      <span class="fragment current-visible" data-fragment-index="3"
            data-set-state="3" data-state-el="#sumlab" data-tokens="3600" data-cost="0.0246"
            data-hint="next turn ~3x cheaper">
        Every future turn sends 3,200 not 12,400 &mdash; <b>~3&times; cheaper</b>, from one small up-front cost.
      </span>
    </div>
  `,
  notes: `The showcase. Step through slowly:
  1) baseline - meter shows 12,400 tokens.
  2) summarize fires - COST jumps +$0.0045 (the summarizer is a real call; we never hide it), tokens unchanged yet.
  3) old messages fold away - TOKENS crash from 12,400 to 3,200 (~74%).
  4) next turn - tokens tiny, cost barely moves.
  The honesty point: a naive demo would hide the summarize cost. We charge it, and it STILL wins.`,
});

Deck.add({
  id: "sum-how",
  html: `
    <div class="slide-head">
      <div class="kicker">01 &middot; Conversation summarization</div>
      <h2>Three rules make it safe</h2>
    </div>
    <div class="icon-rows" style="margin-top:20px;">
      <div class="icon-row wave"><div class="ic">${TW.icon('summarize')}</div><div class="tx"><b>Running summary.</b> Only <em>new</em> messages get folded in each time &mdash; the summarize call stays cheap as history grows.</div></div>
      <div class="icon-row sapphire"><div class="ic">${TW.icon('shield')}</div><div class="tx"><b>Safe cut points.</b> Never separate a tool call from its result &mdash; the provider rejects a broken pair.</div></div>
      <div class="icon-row turmeric"><div class="ic">${TW.icon('cost')}</div><div class="tx"><b>Counted, not hidden.</b> The summarizer's own tokens are billed to the meter &mdash; the savings you saw already include it.</div></div>
    </div>
    <div class="callout" style="margin-top:22px;">The agent's own memory of the conversation is <b>never touched</b> &mdash; only what gets <em>sent</em> per call shrinks.</div>
  `,
  notes: `Shrijayan. Three subtle things that make this correct, not just a demo: (1) fold only what's new so the summarizer cost is bounded; (2) tool_use/tool_result must stay together; (3) the summarize call's tokens are recorded, so cost is honest. All concept - the implementation is one small class in the repo if they want to read it.`,
});

Deck.add({
  id: "sum-notebook",
  html: `
    <div class="center-v">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Measure it: baseline vs. summarized</h2>
      <p class="lead" style="max-width:44ch;">Run the same task twice &mdash; once plain, once with the flag &mdash; and compare tokens &amp; cost.</p>
      <div class="notebook-cue">
        <div class="nb-ic">Jy</div>
        <div class="nb-tx">
          <div class="t">Notebook &rarr; &ldquo;Optimization 1 &mdash; Conversation summarization&rdquo;</div>
          <div class="s">Push history past the threshold, then compare to your baseline run.</div>
        </div>
        <div class="nb-cmd">${TW.techFlag('summarization')}</div>
      </div>
      <p class="muted" style="font-size:0.82em;margin-top:18px;">Expect: fewer tokens per turn, a small one-off summarize cost, and savings that grow with conversation length.</p>
    </div>
  `,
  notes: `Everyone runs it. The deliverable is a before/after comparison. Regroup, ask the room what savings they saw, then hand over for the next technique.`,
});
