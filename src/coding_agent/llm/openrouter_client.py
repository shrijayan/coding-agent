"""Concrete LLMClient for any model hosted on OpenRouter.

OpenRouter exposes one API that proxies hundreds of models (OpenAI,
Google, Meta, Anthropic, ...) behind an OpenAI-compatible Chat
Completions interface. OpenRouter's own docs recommend using the
official `openai` Python SDK pointed at their base URL as a drop-in
replacement - that's what this does, so we get a well-tested SDK
(error types, retries, etc.) instead of hand-rolling HTTP calls.

Like AnthropicClient, this file's job is translating between our
neutral Message format (llm/messages.py) and this provider's wire
format. The two formats differ from Anthropic's in one notable way:
a tool result here is its own message with role="tool", not a content
block folded into a user message.
"""

import json
from typing import Any

import openai

from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart
from coding_agent.metrics.usage import Usage

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient(LLMClient):
    """Sends conversations to whichever model OpenRouter is configured to use."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        self._client = openai.OpenAI(api_key=api_key, base_url=_OPENROUTER_BASE_URL)
        self._model = model
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
        )


def _extract_usage(usage: Any) -> Usage:
    """Some models proxied through OpenRouter occasionally omit usage data
    entirely - treat that as zero rather than crashing, since a missing
    number is a data-completeness gap, not something worth failing over."""
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
    """One neutral Message can expand into several OpenAI-style messages:
    unlike Anthropic, a tool result here needs its own role="tool"
    message rather than being folded into the user turn.
    """
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
    """Turn an OpenAI-SDK-shaped error into one short, human-readable line.

    Note this SDK's .body is already the unwrapped inner error object
    (e.g. {"message": "...", "code": 401}), unlike the anthropic SDK
    whose .body is the full raw response with an "error" key still
    nested inside it - verified by triggering a real 401 against
    OpenRouter rather than assuming the two SDKs behave identically.
    """
    reason = error.message
    body = getattr(error, "body", None)
    if isinstance(body, dict) and body.get("message"):
        reason = str(body["message"])

    status_code = getattr(error, "status_code", None)
    if status_code is not None:
        return f"OpenRouter returned an error ({status_code}): {reason}"
    return f"Could not reach OpenRouter: {reason}"
