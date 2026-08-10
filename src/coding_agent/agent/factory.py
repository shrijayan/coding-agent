"""Builds a fully-wired AgentLoop from config + enabled optimizations.

Pulled out of cli.py so both the interactive REPL and the benchmark
runner (benchmark/runner.py) build an agent exactly the same way - one
place that knows how to assemble an AgentLoop, not two copies that
could quietly drift apart.
"""

from coding_agent.agent.loop import AgentLoop
from coding_agent.config import Config
from coding_agent.llm.base import LLMClient
from coding_agent.llm.factory import build_llm_client
from coding_agent.metrics.cost_guard import CostGuard
from coding_agent.metrics.pricing import PricingTable
from coding_agent.metrics.usage import UsageTracker
from coding_agent.optimizations.bundle import OptimizationBundle
from coding_agent.optimizations.history_policy import DefaultHistoryPolicy
from coding_agent.system_prompt import SYSTEM_PROMPT
from coding_agent.tools.bash import BashTool
from coding_agent.tools.edit_file import EditFileTool
from coding_agent.tools.list_files import ListFilesTool
from coding_agent.tools.read_file import ReadFileTool
from coding_agent.tools.registry import ToolRegistry
from coding_agent.tools.write_file import WriteFileTool


def build_agent(
    config: Config,
    usage_tracker: UsageTracker,
    optimizations: OptimizationBundle,
    pricing: PricingTable | None = None,
) -> AgentLoop:
    """Assemble an AgentLoop wired up with the given config and optimizations.

    Tools always operate relative to the current working directory - the
    interactive REPL runs wherever the user launched it from, and the
    benchmark runner changes into each task's sandboxed repo checkout
    before calling this (see benchmark/runner.py).

    Pass `pricing` to enforce the per-session cost cap (config
    .session_cost_cap_usd); the interactive REPL does, the benchmark
    deliberately doesn't (a controlled measurement shouldn't be cut off
    mid-task by a budget guard).
    """
    llm_client: LLMClient = build_llm_client(config)
    if optimizations.wrap_llm_client is not None:
        llm_client = optimizations.wrap_llm_client(llm_client)

    system_prompt = SYSTEM_PROMPT
    if optimizations.system_prompt_suffix:
        system_prompt = f"{SYSTEM_PROMPT}\n\n{optimizations.system_prompt_suffix}"

    history_policy = optimizations.history_policy or DefaultHistoryPolicy()

    cost_guard: CostGuard | None = None
    if pricing is not None and config.session_cost_cap_usd is not None:
        cost_guard = CostGuard(pricing, config.session_cost_cap_usd)

    tool_registry = ToolRegistry(
        tools=[
            ReadFileTool(),
            WriteFileTool(),
            EditFileTool(),
            BashTool(timeout_seconds=config.bash_timeout_seconds),
            ListFilesTool(),
        ]
    )
    return AgentLoop(
        llm_client=llm_client,
        tool_registry=tool_registry,
        system_prompt=system_prompt,
        max_iterations=config.max_iterations,
        usage_tracker=usage_tracker,
        history_policy=history_policy,
        cost_guard=cost_guard,
    )
