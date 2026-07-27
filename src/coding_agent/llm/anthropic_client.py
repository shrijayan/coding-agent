"""Concrete LLMClient that talks to Claude via the Anthropic Messages API.

This file's only extra job, compared to a direct SDK call, is
translating between our neutral Message format (llm/messages.py) and
Anthropic's own wire format - everything else in the app never sees an
Anthropic-shaped dict.
"""

from typing import Any

import anthropic

from coding_agent.llm.base import LLMClient, LLMError, LLMResponse
from coding_agent.llm.messages import Message, TextPart, ToolResultPart, ToolUsePart


class AnthropicClient(LLMClient):
    """Sends conversations to Claude and normalizes the response."""

    def __init__(self, api_key: str, model: str, max_tokens: int) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def send(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=_to_anthropic_messages(messages),
                tools=tools,
            )
        except anthropic.APIError as error:
            raise LLMError(_describe(error)) from error

        text_parts: list[str] = []
        tool_calls: list[ToolUsePart] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolUsePart(id=block.id, name=block.name, input=block.input)
                )

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            wants_tool_use=(response.stop_reason == "tool_use"),
        )


def _to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    return [_to_anthropic_message(message) for message in messages]


def _to_anthropic_message(message: Message) -> dict[str, Any]:
    content: list[dict[str, Any]] = []

    for part in message.parts:
        if isinstance(part, TextPart):
            content.append({"type": "text", "text": part.text})
        elif isinstance(part, ToolUsePart):
            content.append(
                {
                    "type": "tool_use",
                    "id": part.id,
                    "name": part.name,
                    "input": part.input,
                }
            )
        elif isinstance(part, ToolResultPart):
            content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": part.tool_use_id,
                    "content": part.output,
                    "is_error": part.is_error,
                }
            )

    return {"role": message.role, "content": content}


def _describe(error: anthropic.APIError) -> str:
    """Turn an Anthropic SDK error into one short, human-readable line.

    The SDK's default str(error) includes the full raw response body
    (request IDs, nested dicts, ...) which is noise for an end user - we
    pull out just the actual reason, e.g. "invalid x-api-key".
    """
    reason = error.message
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict) and inner.get("message"):
            reason = str(inner["message"])

    status_code = getattr(error, "status_code", None)
    if status_code is not None:
        return f"Claude API returned an error ({status_code}): {reason}"
    return f"Could not reach Claude: {reason}"
