"""Reusable building blocks for cache-friendly prompt construction.

Split into single-responsibility modules so each can be tested in isolation:
  - layers.py           : PromptLayer + LayerTier (what a chunk is, how stable).
  - serializer.py       : PromptSerializer (deterministic canonical bytes + hash).
  - builder.py          : PromptBuilder + BuiltPrompt (raw send() inputs -> layers).
  - metrics.py          : PromptCacheTracker + PromptCacheRecord (instrumentation).
  - provider_adapter.py : the pluggable seam for provider-specific cache APIs.

The optimization that wires these together lives one level up in
optimizations/cache_friendly.py (the LLMClient wrapper + build()).
"""

from coding_agent.optimizations.prompt_cache.builder import BuiltPrompt, PromptBuilder
from coding_agent.optimizations.prompt_cache.layers import (
    LayerTier,
    PromptLayer,
    is_stable_before_dynamic,
)
from coding_agent.optimizations.prompt_cache.metrics import (
    PromptCacheRecord,
    PromptCacheTracker,
)
from coding_agent.optimizations.prompt_cache.provider_adapter import (
    NoOpProviderCacheAdapter,
    PreparedRequest,
    ProviderCacheAdapter,
)
from coding_agent.optimizations.prompt_cache.serializer import PromptSerializer

__all__ = [
    "BuiltPrompt",
    "LayerTier",
    "NoOpProviderCacheAdapter",
    "PreparedRequest",
    "PromptBuilder",
    "PromptCacheRecord",
    "PromptCacheTracker",
    "PromptLayer",
    "PromptSerializer",
    "ProviderCacheAdapter",
    "is_stable_before_dynamic",
]
