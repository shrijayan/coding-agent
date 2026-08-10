/* ============================================== 20 · CONVERSATION SUMMARIZATION
   Technique #1 - already LIVE in the repo (--enable conversation-summary).
   The centrepiece animation: history collapses into a running summary, the
   HUD's token count drops while the cost ticks up for the summarize call.
   Grounded in optimizations/conversation_summary.py.
============================================================================ */

Deck.add({
  id: "sum-sep",
  hideHud: true,
  html: `
    <div class="separator">
      <div class="txt">
        <div class="idx">Technique 01</div>
        <h1>Conversation<br/>summarization</h1>
        <p>The history re-sent on every turn is the biggest, fastest-growing cost in an agent. So stop re-sending all of it.</p>
        <div style="margin-top:18px;"><span class="pill live"><span class="dot"></span>live in the repo</span></div>
      </div>
      <div class="visual teal">
        <div style="text-align:center;color:#eaf4f6;">
          <div style="font-size:3em;color:#ff8ea1;">${TW.icon('summarize')}</div>
          <div style="font-family:var(--tw-mono);font-size:0.72em;margin-top:12px;color:#9fb6bd;">--enable conversation-summary</div>
        </div>
      </div>
    </div>
  `,
  notes: `Presenter One. The problem in one line: every turn re-sends the whole transcript, and the transcript only grows. Summarization caps that.`,
});

Deck.add({
  id: "sum-lab",
  hideHud: false,
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
            User is refactoring auth: created <b>auth.py</b>, edited <b>login.py</b>, ran <b>pytest</b> &rarr; 3 passed. Still open: wire the logout route.
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
          <span class="lb"><b>Summarizer</b>one extra model call, folds only what's new</span>
        </div>
        <div class="ba">
          <div class="row before"><span class="lab">sent / turn &mdash; before</span><span class="v">12,400 tok</span></div>
          <div class="row cost"><span class="lab">the summarize call</span><span class="v">+ $0.0045</span></div>
          <div class="row after"><span class="lab">sent / turn &mdash; after</span><span class="v">3,200 tok</span></div>
        </div>
      </div>
    </div>

    <div class="stepline" style="margin-top:14px;min-height:2.1em;font-size:0.86em;color:var(--tw-ink-soft);">
      <span class="fragment current-visible" data-fragment-index="0"
            data-set-state="1" data-state-el="#sumlab" data-tokens="12400" data-cost="0.0182"
            data-hint="history is re-sent every single turn">
        Every turn re-sends the <b>entire</b> transcript &mdash; and it only grows. &#8599; watch the meter.
      </span>
      <span class="fragment current-visible" data-fragment-index="1"
            data-set-state="2" data-state-el="#sumlab" data-tokens="12400" data-cost="0.0227"
            data-hint="summarizer call = +$0.0045 once">
        Past the threshold, fold the old messages into one summary &mdash; itself a real, <b>paid</b> model call.
      </span>
      <span class="fragment current-visible" data-fragment-index="2"
            data-set-state="3" data-state-el="#sumlab" data-tokens="3200" data-cost="0.0227"
            data-hint="context shrinks ~74%">
        Old turns collapse into the running summary; only the recent few stay verbatim. <b>Tokens drop 74%.</b>
      </span>
      <span class="fragment current-visible" data-fragment-index="3"
            data-set-state="3" data-state-el="#sumlab" data-tokens="3600" data-cost="0.0246"
            data-hint="next turn ~3x cheaper">
        Every future turn now sends 3,200 not 12,400 &mdash; <b>~3&times; cheaper</b>, for one small up-front cost.
      </span>
    </div>
  `,
  notes: `The showcase. Step through slowly:
  1) baseline - meter shows 12,400 tokens.
  2) summarize fires - COST jumps +$0.0045 (the summarizer is a real call; we never hide it), tokens unchanged yet.
  3) old messages fold away - TOKENS crash from 12,400 to 3,200 (~74%).
  4) next turn - tokens tiny, cost barely moves. The trade you're buying: pay a little once, save on every turn after.
  The honesty point: a naive demo would hide the summarize cost. We charge it, and it STILL wins.`,
});

Deck.add({
  id: "sum-code",
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">optimizations/conversation_summary.py</div>
      <h2>How it plugs in &mdash; a HistoryPolicy</h2>
    </div>
    <div class="split top" style="grid-template-columns:1.25fr 0.75fr;">
      <div class="col">
        <div class="code-panel">
          <div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="fn">conversation_summary.py</span></div>
          <pre><code class="language-python" data-trim data-noescape>def prepare(self, messages, context):
    if len(messages) <= self.threshold_messages:
        return messages                     # nothing to do yet

    keep_from = _safe_keep_from(            # never split a tool_use
        messages, len(messages) - self.keep_recent_messages)
    new = messages[self._summarized_through : keep_from]

    if new:                                 # only fold what's NEW
        self._summary = self._summarize(new, context)
        self._summarized_through = keep_from

    summary_msg = Message("user", [TextPart(self._summary)])
    return [summary_msg, *messages[keep_from:]]  # summary + recent</code></pre>
        </div>
      </div>
      <div class="col">
        <div class="stack-sm">
          <div class="callout"><b>Running summary.</b> Only messages since the last summary are folded in &mdash; the summarize call stays cheap as history grows.</div>
          <div class="callout" style="border-left-color:var(--tw-teal);"><b>Safe cut points.</b> Never split a <code>tool_use</code> from its <code>tool_result</code>, or the API rejects the turn.</div>
          <div class="callout" style="border-left-color:var(--tw-amber);"><b>Counted, not hidden.</b> The summarize call records its real usage &mdash; the meter you saw includes it.</div>
        </div>
      </div>
    </div>
  `,
  notes: `Presenter One. Three subtle things that make this correct, not just a demo: (1) fold only what's new so the summarizer cost is bounded; (2) tool_use/tool_result must stay together; (3) the summarize call's tokens are recorded, so cost is honest.`,
});

Deck.add({
  id: "sum-notebook",
  hideHud: false,
  html: `
    <div class="slide-head">
      <div class="kicker">Your turn &mdash; hands on</div>
      <h2>Measure it: baseline vs. summarized</h2>
    </div>
    <p class="lead" style="max-width:42ch;">Run the same task twice &mdash; once plain, once with the flag &mdash; and compare <code>/usage</code>.</p>
    <div class="notebook-cue">
      <div class="nb-ic">Jupyter</div>
      <div class="nb-tx">
        <div class="t">Notebook &rarr; &ldquo;Optimization 1 &mdash; Conversation summarization&rdquo;</div>
        <div class="s">Push history past the threshold, then read tokens &amp; cost. Compare to your baseline run.</div>
      </div>
      <div class="nb-cmd">uv run coding-agent --enable conversation-summary</div>
    </div>
    <p class="muted" style="font-size:0.8em;margin-top:16px;">Expect: fewer tokens per turn, a small one-off summarize cost, and net savings that grow with conversation length.</p>
  `,
  notes: `Everyone runs it. The deliverable is a before/after /usage screenshot. Regroup, ask the room what savings they saw, then hand to Presenter One/Two for the next technique.`,
});
