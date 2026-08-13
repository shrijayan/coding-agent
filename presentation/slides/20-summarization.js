/* ============================================== 20 · CONVERSATION SUMMARIZATION
   Technique #1 - LIVE in the repo. The centrepiece animation: history
   collapses into a running summary, tokens drop while cost ticks up for the
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
