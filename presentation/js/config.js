/* =========================================================================
   Talk-level config: speakers and technique metadata.
   Loaded BEFORE components.js, which reads these to render the repeated
   bits (presenter cards, status pills, --enable flags, recap rows) so
   updating a name or flipping a status happens in ONE place instead of
   drifting across slides/*.js.

   Bespoke per-slide content (taglines, diagrams, lab animations) stays
   hand-written in the slide files - only the data that repeats lives here.
   ========================================================================= */

window.SPEAKERS = [
  { id: "adithya", name: "Adithya K P", role: "M L Engineer", org: "Thoughtworks" },
  { id: "krishna", name: "P D Krishna Chaitanya", role: "AI Engineer", org: "Thoughtworks" },
  { id: "shrijayan", name: "Shrijayan Rajendran", role: "AI Engineer", org: "Thoughtworks", ownsBaseAgent: true },
];

// Keyed by the id each slide file uses to look itself up (TW.techMeta("routing"), ...).
// `primary: true` marks the six techniques listed on the recap slide;
// sub-techniques (like cache-friendly, technique 02b) are omitted there.
// context-window used to be one technique (05) covering two mechanisms; it's
// split into 05a/05b because context_window.py really does run them as two
// separate things - one always-on (pruning, via history_policy), one gated
// by its own independent env var (skills, via extra_tools) - and the
// notebook demonstrates each in its own dedicated cell/scenario, not just
// prose. Same --enable flag for both: there's no separate registered
// optimization the way cache-friendly-prompts has its own.
window.TECHNIQUES = {
  summarization: {
    number: "01",
    title: "Conversation summarization",
    status: "live",
    flag: "--enable conversation-summary",
    accent: "sapphire",
    owner: "shrijayan",
    icon: "summarize",
    meterNote: "tokens ↓↓ per turn, one-off summarize cost",
    primary: true,
  },
  "prompt-caching": {
    number: "02",
    title: "Prompt optimization &amp; caching",
    status: "live",
    flag: "--enable cache-friendly-prompts",
    accent: "turmeric",
    owner: "krishna",
    icon: "cache",
    meterNote: "cost growth flattens on repeated prefixes",
    primary: true,
  },
  "cache-friendly": {
    number: "02b",
    title: "Cache-friendly prompts",
    status: "live",
    flag: "--enable cache-friendly-prompts",
    accent: "turmeric",
    owner: "krishna",
    primary: false,
  },
  routing: {
    number: "03",
    title: "Model selection &amp; routing",
    status: "live",
    flag: "--enable hybrid-routing",
    accent: "jade",
    owner: "krishna",
    icon: "route",
    meterNote: "cost ↓ — cheap model does the easy work",
    primary: true,
  },
  "loop-prevention": {
    number: "04",
    title: "Agent loop prevention",
    status: "live",
    flag: "--enable loop-guard",
    accent: "flamingo",
    owner: "adithya",
    icon: "loop",
    meterNote: "caps runaway cost when the agent spins",
    primary: true,
  },
  "context-pruning": {
    number: "05a",
    title: "Context pruning",
    status: "live",
    flag: "--enable context-window",
    accent: "amethyst",
    owner: "adithya",
    icon: "context",
    meterNote: "tokens ↓ by pruning stale, bulky tool output",
    primary: true,
  },
  "context-skills": {
    number: "05b",
    title: "Skills, loaded on demand",
    status: "live",
    flag: "--enable context-window",
    accent: "sapphire",
    owner: "adithya",
    icon: "stack",
    meterNote: "guidance loads only when load_skill() is actually called",
    primary: true,
  },
};
