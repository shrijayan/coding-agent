/* =========================================================================
   The deck engine.
   - Slides register themselves with Deck.add({...}) from slides/*.js
     (loaded in order via <script> tags in index.html => that IS the deck
     order; reorder a talk by reordering those tags).
   - build() wraps each registration into a <section>, wires reveal.js, and
     keeps the persistent chrome (HUD / logo / footer) in sync with the
     current slide via a single, declarative update() pass.

   DECLARATIVE HOOKS a slide can put on its <section> (via the def object)
   or on any .fragment inside it:
     section def:  dark, hideHud, hideChrome, tokens, cost, notes
     fragment:     data-tokens / data-cost   -> HUD jumps to these when shown
                   data-hint "text"          -> shows the HUD side-caption
                   data-set-state N + data-state-el "#sel"
                                             -> sets [data-state] on a visual
     any element:  data-state-initial N      -> its resting state
   update() recomputes all of the above from whichever fragments are
   currently visible, so forward AND backward navigation stay correct.
   ========================================================================= */
(function () {
  "use strict";

  const registrations = [];
  const hooksById = {};
  let LAST = { tokens: 0, cost: 0 };
  let prevSection = null;

  const Deck = {
    add(def) {
      if (!def || !def.html) throw new Error("Deck.add needs { html }");
      registrations.push(def);
    },
    build() { assemble(); initReveal(); },
  };

  function assemble() {
    const container = document.querySelector(".reveal .slides");
    registrations.forEach((def, i) => {
      const s = document.createElement("section");
      s.dataset.id = def.id || "slide-" + i;
      if (def.dark) {
        s.classList.add("dark");
        // dark slides need a real dark BACKGROUND, not just light text
        s.setAttribute("data-background-color", def.bg || "#003d4f");
      } else if (def.bg) {
        s.setAttribute("data-background-color", def.bg);
      }
      if (def.hideHud) s.dataset.hideHud = "1";
      if (def.hideChrome) s.dataset.hideChrome = "1";
      if (def.tokens != null) s.dataset.tokens = def.tokens;
      if (def.cost != null) s.dataset.cost = def.cost;
      s.innerHTML = `<div class="pad">${def.html}</div>`;
      if (def.notes) {
        const aside = document.createElement("aside");
        aside.className = "notes";
        aside.innerHTML = def.notes;
        s.appendChild(aside);
      }
      container.appendChild(s);
      hooksById[s.dataset.id] = { onEnter: def.onEnter, onLeave: def.onLeave };
    });
  }

  function initReveal() {
    Reveal.initialize({
      width: 1280,
      height: 720,
      margin: 0.045,
      minScale: 0.2,
      maxScale: 2.0,
      hash: true,
      slideNumber: "c/t",
      transition: "slide",
      transitionSpeed: "default",
      backgroundTransition: "fade",
      controls: true,
      controlsTutorial: false,
      progress: true,
      center: false,
      plugins: [RevealHighlight, RevealNotes],
    });
    HUD.init();
    Reveal.on("ready", update);
    Reveal.on("slidechanged", update);
    Reveal.on("fragmentshown", update);
    Reveal.on("fragmenthidden", update);
  }

  function visibleFragments(section) {
    // DOM order approximates fragment order (slides author fragments in order)
    return Array.from(section.querySelectorAll(".fragment.visible"));
  }

  function update() {
    const section = Reveal.getCurrentSlide();
    if (!section) return;

    // ---- per-slide chrome -------------------------------------------------
    const dark = section.classList.contains("dark");
    document.body.classList.toggle("chrome-dark", dark);
    document.body.classList.toggle("dark-chrome", dark);
    document.body.classList.toggle("chrome-hidden", section.dataset.hideChrome === "1");
    if (section.dataset.hideHud === "1") HUD.hide(); else HUD.show();

    // ---- onLeave / onEnter hooks -----------------------------------------
    if (prevSection && prevSection !== section) {
      const h = hooksById[prevSection.dataset.id];
      if (h && h.onLeave) try { h.onLeave(prevSection); } catch (e) { console.warn(e); }
    }
    if (prevSection !== section) {
      const h = hooksById[section.dataset.id];
      if (h && h.onEnter) try { h.onEnter(section); } catch (e) { console.warn(e); }
    }
    prevSection = section;

    // ---- resolve visual [data-state] targets -----------------------------
    const stateTargets = new Map();
    section.querySelectorAll("[data-state-initial]").forEach((el) => {
      stateTargets.set(el, +el.dataset.stateInitial);
    });

    // ---- resolve HUD + hint from visible fragments -----------------------
    let tokens = section.dataset.tokens != null ? +section.dataset.tokens : LAST.tokens;
    let cost = section.dataset.cost != null ? +section.dataset.cost : LAST.cost;
    let hint = null;

    for (const f of visibleFragments(section)) {
      if (f.dataset.tokens != null) tokens = +f.dataset.tokens;
      if (f.dataset.cost != null) cost = +f.dataset.cost;
      if (f.dataset.hint != null) hint = f.dataset.hint;
      if (f.dataset.setState != null && f.dataset.stateEl) {
        const el = section.querySelector(f.dataset.stateEl);
        if (el) stateTargets.set(el, +f.dataset.setState);
      }
    }

    stateTargets.forEach((state, el) => { el.dataset.state = state; });

    LAST = { tokens, cost };
    if (section.dataset.hideHud !== "1") HUD.set(tokens, cost, { animate: true });
    HUD.hintText(hint);
  }

  window.Deck = Deck;
  // index.html calls Deck.build() once, AFTER every slides/*.js has run and
  // registered - so registration order is exactly the <script> tag order.
})();
