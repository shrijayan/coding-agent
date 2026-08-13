/* =========================================================================
   HUD controller: the top-right TOKENS + COST readout.
   Slides/fragments never touch this directly - deck.js reads data-* on the
   current slide and calls HUD.set(tokens, cost). Numbers tween so they feel
   alive (tokens dropping after a summarize, cost ticking up on every call).
   ========================================================================= */
(function () {
  "use strict";

  function fmtInt(n) {
    return Math.round(n).toLocaleString("en-US");
  }
  function fmtCost(n) {
    // 4 dp reads well for the sub-cent amounts a workshop session produces
    return "$" + n.toFixed(4);
  }
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  const HUD = {
    el: null,
    tokensNum: null,
    costNum: null,
    tokensDelta: null,
    costDelta: null,
    tokensStat: null,
    costStat: null,
    hint: null,
    cur: { tokens: 0, cost: 0 },
    peakTokens: 1,
    _raf: { tokens: null, cost: null },

    init() {
      this.el = document.getElementById("hud");
      if (!this.el) return;
      this.tokensStat = this.el.querySelector(".hud-stat.tokens");
      this.costStat = this.el.querySelector(".hud-stat.cost");
      this.tokensNum = this.el.querySelector(".tokens .num");
      this.costNum = this.el.querySelector(".cost .num");
      this.tokensDelta = this.el.querySelector(".tokens .hud-delta");
      this.costDelta = this.el.querySelector(".cost .hud-delta");
      this.hint = document.getElementById("hud-hint");
      this._render();
    },

    show() { this.el && this.el.classList.remove("is-hidden"); },
    hide() { this.el && this.el.classList.add("is-hidden"); },

    hintText(txt) {
      if (!this.hint) return;
      if (txt) { this.hint.textContent = txt; this.hint.classList.add("show"); }
      else { this.hint.classList.remove("show"); }
    },

    _render() {
      if (this.tokensNum) this.tokensNum.textContent = fmtInt(this.cur.tokens);
      if (this.costNum) this.costNum.textContent = this.cur.cost.toFixed(4);
    },

    _flash(stat) {
      if (!stat) return;
      stat.classList.remove("flash");
      // reflow to restart the animation
      void stat.offsetWidth;
      stat.classList.add("flash");
    },

    _delta(el, diff, kind) {
      if (!el) return;
      if (Math.abs(diff) < (kind === "cost" ? 0.00005 : 0.5)) {
        el.classList.remove("show", "good", "bad");
        return;
      }
      const decreased = diff < 0;
      // tokens: fewer is GOOD (savings). cost: more is the cost of the call.
      const good = kind === "tokens" ? decreased : diff < 0;
      const arrow = decreased ? "\u25BC" : "\u25B2";
      const mag = kind === "cost" ? "$" + Math.abs(diff).toFixed(4) : fmtInt(Math.abs(diff));
      el.textContent = arrow + " " + mag;
      el.classList.remove("good", "bad");
      el.classList.add(good ? "good" : "bad", "show");
      // persist the delta so the audience can keep tracking the +/- change
      clearTimeout(el._t);
    },

    _tweenField(field, to, dur, apply) {
      if (this._raf[field]) cancelAnimationFrame(this._raf[field]);
      const from = this.cur[field];
      if (dur <= 0 || Math.abs(to - from) < 1e-9) {
        this.cur[field] = to; apply(to); return;
      }
      const start = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - start) / dur);
        const v = from + (to - from) * easeOutCubic(t);
        this.cur[field] = v;
        apply(v);
        if (t < 1) this._raf[field] = requestAnimationFrame(step);
      };
      this._raf[field] = requestAnimationFrame(step);
    },

    /* The one method deck.js calls. animate=false snaps instantly. */
    set(tokens, cost, opts) {
      opts = opts || {};
      const animate = opts.animate !== false;
      const dur = opts.duration != null ? opts.duration : 900;

      if (typeof tokens === "number" && !Number.isNaN(tokens)) {
        const diff = tokens - this.cur.tokens;
        this.peakTokens = Math.max(this.peakTokens, tokens, this.cur.tokens);
        this._tweenField("tokens", tokens, animate ? dur : 0, (v) => {
          if (this.tokensNum) this.tokensNum.textContent = fmtInt(v);
        });
        if (opts.showDelta !== false) this._delta(this.tokensDelta, diff, "tokens");
        if (Math.abs(diff) > 0.5) this._flash(this.tokensStat);
      }
      if (typeof cost === "number" && !Number.isNaN(cost)) {
        const diff = cost - this.cur.cost;
        this._tweenField("cost", cost, animate ? dur : 0, (v) => {
          if (this.costNum) this.costNum.textContent = v.toFixed(4);
        });
        if (opts.showDelta !== false) this._delta(this.costDelta, diff, "cost");
        if (Math.abs(diff) > 0.00005) this._flash(this.costStat);
      }
    },
  };

  window.HUD = HUD;
})();
