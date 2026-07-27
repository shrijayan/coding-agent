"""Maps --enable names to the optimization they turn on."""

from collections.abc import Callable

from coding_agent.optimizations.bundle import OptimizationBundle


class UnknownOptimizationError(RuntimeError):
    """Raised when --enable names something that isn't registered.

    A typo in --enable should never silently run with no optimization
    applied - that would make a workshop demo quietly meaningless.
    """


class OptimizationRegistry:
    """A lookup table from optimization name -> factory function.

    Mirrors ToolRegistry and SlashCommandRegistry: optimizations are
    passed in from outside (constructor injection) as a name -> factory
    dict; this class only knows how to look them up, resolve, and
    combine them - not how to build any particular one. Building a new
    optimization never means touching this file - see AGENTS.md's
    "How to add a new optimization".
    """

    def __init__(self, factories: dict[str, Callable[[], OptimizationBundle]]) -> None:
        self._factories = factories

    def resolve(self, names: list[str]) -> OptimizationBundle:
        """Combine every named optimization into one bundle.

        Fails fast on any unregistered name, and on any two enabled
        optimizations that conflict (see OptimizationBundle.merged_with).
        """
        combined = OptimizationBundle()
        for name in names:
            factory = self._factories.get(name)
            if factory is None:
                available = ", ".join(sorted(self._factories)) or "(none registered yet)"
                raise UnknownOptimizationError(
                    f"Unknown optimization: '{name}'. Available: {available}"
                )
            combined = combined.merged_with(factory())
        return combined
