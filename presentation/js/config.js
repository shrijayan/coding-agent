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
// `primary: true` marks the five techniques listed on the agenda/recap slides;
// sub-techniques (like cache-friendly, technique 02b) are omitted there.
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
  "context-window": {
    number: "04",
    title: "Context window optimization",
    status: "live",
    flag: "--enable context-window",
    accent: "amethyst",
    owner: "adithya",
    icon: "context",
    meterNote: "tokens ↓ by pruning irrelevant context",
    primary: true,
  },
  "loop-prevention": {
    number: "05",
    title: "Agent loop prevention",
    status: "live",
    flag: "--enable loop-guard",
    accent: "flamingo",
    owner: "adithya",
    icon: "loop",
    meterNote: "caps runaway cost when the agent spins",
    primary: true,
  },
};
