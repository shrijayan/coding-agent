/* =========================================================================
   Small presentation helpers shared by every slide module.
   window.TW.icon(name) returns a clean inline SVG (stroke = currentColor)
   so the coloured icon cells in layouts stay crisp at any projector size,
   with no emoji-font roulette. Loaded BEFORE slides/*.js in index.html.
   ========================================================================= */
(function () {
  "use strict";

  const P = { fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" };
  function svg(paths) {
    const a = Object.entries(P).map(([k, v]) => `${k}="${v}"`).join(" ");
    // width/height via inline STYLE (em as an SVG geometry attribute isn't
    // reliably honored; as a CSS length it is) so icons scale with font-size.
    return `<svg viewBox="0 0 24 24" style="width:1em;height:1em;display:inline-block;vertical-align:-0.14em;flex:none" ${a}>${paths}</svg>`;
  }

  const ICONS = {
    summarize: '<path d="M4 6h16"/><path d="M4 10h16"/><path d="M4 14h10"/><path d="M4 18h6"/><path d="M15 17l3 3 3-4"/>',
    cache:     '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
    route:     '<circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="18" r="2.4"/><path d="M6 8.4V15c0 1.6 1.3 3 3 3h6.6"/><path d="M18 15.6V12a4 4 0 0 0-4-4H8.4"/>',
    context:   '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 9l-2 3 2 3"/><path d="M16 9l2 3-2 3"/>',
    loop:      '<path d="M4 12a8 8 0 0 1 13.7-5.6L20 8"/><path d="M20 4v4h-4"/><path d="M20 12a8 8 0 0 1-13.7 5.6L4 16"/><path d="M4 20v-4h4"/>',
    agent:     '<rect x="5" y="7" width="14" height="12" rx="2"/><path d="M9 7V4h6v3"/><circle cx="9.5" cy="13" r="1"/><circle cx="14.5" cy="13" r="1"/><path d="M2 12h3M19 12h3"/>',
    tokens:    '<path d="M6 4l-2 16M14 4l-2 16M4 9h16M3 15h16"/>',
    cost:      '<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.2c0-1.2 1.1-2 2.5-2s2.5.8 2.5 2-1.1 1.8-2.5 1.8-2.5.7-2.5 1.9 1.1 2 2.5 2 2.5-.8 2.5-2"/>',
    bolt:      '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    check:     '<circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.5 2.5 5-5.5"/>',
    gauge:     '<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4-5"/><circle cx="12" cy="18" r="1.4"/>',
    shield:    '<path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9.5 12l2 2 3.5-4"/>',
    scissors:  '<circle cx="6" cy="6" r="2.6"/><circle cx="6" cy="18" r="2.6"/><path d="M8 8l12 10M8 16L20 6"/>',
    stack:     '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  };

  // Short pill copy per status, for the two contexts that use it: the
  // separator's own pill ("live in the repo") and the compact recap-table /
  // agenda-list pill ("live"). Pass a label to override either.
  const PILL_LABEL = { live: "live in the repo", wip: "in progress", planned: "planned" };
  const PILL_LABEL_SHORT = { live: "live", wip: "building", planned: "planned" };

  function tech(id) {
    const t = window.TECHNIQUES && window.TECHNIQUES[id];
    if (!t) throw new Error(`TW: unknown technique id "${id}"`);
    return t;
  }

  window.TW = {
    icon(name) { return svg(ICONS[name] || ICONS.check); },
    escape(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); },

    // ---- speakers -----------------------------------------------------
    speakerByline(sep) {
      return window.SPEAKERS.map((s) => s.name).join(sep || " &middot; ");
    },
    // Full titles of the primary techniques a speaker owns, joined for a
    // presenter card / thank-you slide - derived from TECHNIQUES so it can
    // never drift from what the agenda/recap actually list.
    speakerOwns(speakerId) {
      return Object.values(window.TECHNIQUES)
        .filter((t) => t.owner === speakerId && t.primary)
        .map((t) => t.title)
        .join(" &middot; ");
    },
    presenterCards() {
      const letters = ["a", "b", "c"];
      return window.SPEAKERS.map((s, i) => `
        <div class="presenter ${letters[i] || "a"}">
          <div class="avatar"></div>
          <div class="pname">${s.name}</div>
          <div class="prole">${s.role} &middot; ${s.org}</div>
          <div class="powns">${TW.speakerOwns(s.id)}</div>
        </div>`).join("");
    },

    // ---- techniques -----------------------------------------------------
    pill(status, label) {
      return `<span class="pill ${status}"><span class="dot"></span>${label || PILL_LABEL[status] || status}</span>`;
    },
    techAccent(id) { return `var(--tw-${tech(id).accent})`; },
    techIdx(id) { return `Technique ${tech(id).number}`; },
    techTitle(id) { return tech(id).title; },
    techFlag(id) { return tech(id).flag; },
    // The pill + --enable flag block every separator slide shows.
    techMeta(id) {
      const t = tech(id);
      return `<div class="sep-meta">${TW.pill(t.status)}<div class="flag">${t.flag}</div></div>`;
    },
    // One row of the agenda's "Five techniques" list (00-intro.js).
    agendaRow(id) {
      const t = tech(id);
      return `<div>${TW.pill(t.status, PILL_LABEL_SHORT[t.status])} &nbsp;${t.title}</div>`;
    },
    // One row of the closing recap table (90-closing.js).
    recapRow(id) {
      const t = tech(id);
      return `<tr><td><b>${t.title}</b></td><td>${TW.pill(t.status, PILL_LABEL_SHORT[t.status])}</td><td>${t.meterNote}</td></tr>`;
    },
  };
})();
