"""Concrete LLMClient for a local, free cheap-tier model served by Ollama.

Ollama ships an OpenAI-compatible Chat Completions API at
http://localhost:11434/v1, so this reuses the already-present `openai`
SDK pointed at that base URL - exactly the same trick OpenRouterClient
uses, just aimed at localhost instead. That keeps the cheap tier behind
the same LLMClient abstraction as every other provider (no LiteLLM, no
parallel code path), which is what lets the hybrid-routing wrapper treat
"cheap" and "powerful" as interchangeable LLMClients.

The two provider-specific jobs are the same as OpenRouterClient's:
translate our neutral Message format (llm/messages.py) to/from the
OpenAI wire format, and turn the SDK's exceptions into a clean LLMError.
The one Ollama-specific concern is that a local Ollama simply not
running is the *common* failure here (unlike a hosted API), so an
unreachable endpoint must surface as an ordinary LLMError the caller can
recover from - never an uncaught crash mid-demo.
"""

import json
from typing import Any

import openai

from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage

# Ollama ignores the API key, but the openai SDK requires a non-empty one.
_OLLAMA_API_KEY = "ollama"

# Config carries the model as e.g. "ollama/qwen2.5-coder:7b" so the same
# string can key the models.yaml catalog; Ollama's own API wants just the
# bare model name, so this prefix is stripped before the call.
_MODEL_PREFIX = "ollama/"


class OllamaClient(LLMClient):
    """Sends conversations to a local Ollama model and normalizes the response."""

    def __init__(self, base_url: str, model: str, max_tokens: int) -> None:
        self._client = openai.OpenAI(api_key=_OLLAMA_API_KEY, base_url=base_url)
        # Keep the prefixed form too: it's the models.yaml catalog key
        # reported in LLMResponse.model, while the API wants the bare name.
        self._model_id = model
        self._model = _strip_prefix(model)
        self._max_tokens = max_tokens

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        openai_messages = [
            {"role": "system", "content": system},
            *_to_openai_messages(messages),
        ]

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=openai_messages,
                tools=[_to_openai_tool(tool) for tool in tools],
            )
        except openai.APIError as error:
            raise LLMError(_describe(error)) from error

        message = response.choices[0].message
        tool_calls = [
            ToolUsePart(
                id=call.id,
                name=call.function.name,
                input=json.loads(call.function.arguments or "{}"),
            )
            for call in (message.tool_calls or [])
        ]

        return LLMResponse(
            text=message.content or "",
            tool_calls=tool_calls,
            wants_tool_use=bool(tool_calls),
            usage=_extract_usage(response.usage),
            model=self._model_id,
        )


def _strip_prefix(model: str) -> str:
    return model.removeprefix(_MODEL_PREFIX)


def _extract_usage(usage: Any) -> Usage:
    """Real token counts from Ollama's response - never estimated (see
    LLMResponse.usage). A missing usage block is treated as zero rather
    than crashing, same as OpenRouterClient."""
    if usage is None:
        return Usage()
    return Usage(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens)


def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Our neutral {name, description, input_schema} -> OpenAI's nested shape."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


def _to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        result.extend(_to_openai_turns(message))
    return result


def _to_openai_turns(message: Message) -> list[dict[str, Any]]:
    """One neutral Message can expand into several OpenAI-style messages -
    identical translation to OpenRouterClient's, since Ollama speaks the
    same OpenAI wire format (tool results are their own role="tool"
    messages, not folded into a user turn)."""
    text = "\n".join(part.text for part in message.parts if isinstance(part, TextPart))
    tool_uses = [part for part in message.parts if isinstance(part, ToolUsePart)]
    tool_results = [part for part in message.parts if isinstance(part, ToolResultPart)]

    turns: list[dict[str, Any]] = []

    if message.role == "assistant":
        assistant_turn: dict[str, Any] = {"role": "assistant", "content": text or None}
        if tool_uses:
            assistant_turn["tool_calls"] = [
                {
                    "id": part.id,
                    "type": "function",
                    "function": {"name": part.name, "arguments": json.dumps(part.input)},
                }
                for part in tool_uses
            ]
        turns.append(assistant_turn)
    elif text:
        turns.append({"role": "user", "content": text})

    turns.extend(
        {"role": "tool", "tool_call_id": part.tool_use_id, "content": part.output}
        for part in tool_results
    )

    return turns


def _describe(error: openai.APIError) -> str:
    """Turn an openai-SDK error into one short, human-readable line.

    The most likely error here is Ollama not running at all, which the
    SDK raises as an APIConnectionError (no status code) - phrase that
    case as an actionable hint rather than a raw stack trace.
    """
    status_code = getattr(error, "status_code", None)
    reason = error.message
    body = getattr(error, "body", None)
    if isinstance(body, dict) and body.get("message"):
        reason = str(body["message"])

    if status_code is not None:
        return f"Ollama returned an error ({status_code}): {reason}"
    return (
        f"Could not reach Ollama at its configured base URL ({reason}). "
        "Is `ollama serve` running and the cheap model pulled "
        "(e.g. `ollama pull qwen2.5-coder:7b`)?"
    )
