"""The core agent loop: LLM <-> tools, repeated until there's a final answer.

This is the piece everything else in the project exists to support. It
knows nothing about Anthropic specifically (it depends on the LLMClient
abstraction), nothing about which tools exist (it depends on
ToolRegistry), and nothing about any optimization that's enabled (it
depends on HistoryPolicy, and just calls whichever LLMClient it was
handed - a caching/routing wrapper looks identical to it). That's
dependency inversion in practice: swap any of them out and this file
does not change - which is exactly what lets every workshop
optimization plug in without touching this file.
"""

from collections.abc import Callable

from coding_agent.agent.conversation import Conversation
from coding_agent.llm.base import LLMClient
from coding_agent.metrics.cost_guard import CostGuard
from coding_agent.metrics.usage import UsageTracker
from coding_agent.optimizations.history_policy import HistoryContext, HistoryPolicy
from coding_agent.tools.registry import ToolExecutor

# Called as on_tool_call(tool_name, tool_input) right before each tool runs,
# so the CLI can show the user what's happening. Optional - the loop works
# fine without a listener, it just runs quietly.
ToolCallObserver = Callable[[str, dict], None]


class AgentLoopSafetyLimitError(RuntimeError):
    """Raised when the model keeps requesting tools without ever finishing.

    This is a safety net, not an expected outcome - if you hit it
    regularly, raise AGENT_MAX_ITERATIONS or look at why the model isn't
    converging on an answer.
    """


class AgentLoop:
    """Runs one user turn to completion, handling any number of tool calls."""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolExecutor,
        system_prompt: str,
        max_iterations: int,
        usage_tracker: UsageTracker,
        history_policy: HistoryPolicy,
        cost_guard: CostGuard | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._tool_registry = tool_registry
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._usage_tracker = usage_tracker
        self._history_policy = history_policy
        self._cost_guard = cost_guard
        self.conversation = Conversation()

    def run_turn(
        self,
        user_input: str,
        on_tool_call: ToolCallObserver | None = None,
    ) -> str:
        """Send one user message and return the model's final text answer.

        Internally this may call the model several times: each time it
        asks for a tool, we run the tool, feed the result back, and ask
        again - until it responds with plain text instead of a tool call.
        """
        self.conversation.add_user_text(user_input)
        self._usage_tracker.record_user_message()
        history_context = HistoryContext(
            llm_client=self._llm_client,
            usage_tracker=self._usage_tracker,
        )

        for _ in range(self._max_iterations):
            # Soft budget guard: stop before the next call once the session
            # has spent its cap, rather than quietly running a shared budget
            # down (see metrics/cost_guard.py).
            if self._cost_guard is not None and self._cost_guard.exceeded(
                self._usage_tracker
            ):
                return self._cost_guard.notice(self._usage_tracker)

            messages_to_send = self._history_policy.prepare(
                self.conversation.messages, history_context
            )
            response = self._llm_client.send(
                system=self._system_prompt,
                messages=messages_to_send,
                tools=self._tool_registry.definitions(),
            )
            self._usage_tracker.record_llm_call(response.usage, response.model)
            self.conversation.add_assistant_turn(response.text, response.tool_calls)

            if not response.wants_tool_use:
                return response.text

            results = []
            for call in response.tool_calls:
                if on_tool_call is not None:
                    on_tool_call(call.name, call.input)
                result = self._tool_registry.execute(call.name, call.input)
                self._usage_tracker.record_tool_call()
                results.append((call.id, result))

            self.conversation.add_tool_results(results)

        raise AgentLoopSafetyLimitError(
            f"Stopped after {self._max_iterations} tool-use round-trips "
            "without a final answer. Increase AGENT_MAX_ITERATIONS if this "
            "task genuinely needs more steps."
        )
