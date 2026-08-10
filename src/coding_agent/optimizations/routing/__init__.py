"""Supporting modules for the hybrid-routing optimization.

Split one-responsibility-per-file (per AGENTS.md):
  - features.py     : free local feature extraction from the request
  - router.py       : difficulty scorer (features -> 0.0-1.0 score)
  - quality_gate.py : deterministic post-generation check on cheap output
  - metrics.py      : RoutingTracker, the in-memory per-send record store

The wrapper that ties them together lives one level up in
optimizations/hybrid_routing.py.
"""
