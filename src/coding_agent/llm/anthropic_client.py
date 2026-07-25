"""Concrete LLMClient that talks to Claude via the Anthropic Messages API."""

from typing import Any

import anthropic

from coding_agent.llm.base import LLMClient, LLMError, LLMResponse, ToolCall


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
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except anthropic.APIError as error:
            raise LLMError(_describe(error)) from error

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_content: list[dict[str, Any]] = []

        for block in response.content:
            raw_content.append(block.model_dump())
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=block.input)
                )

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            raw_content=raw_content,
            stop_reason=response.stop_reason or "end_turn",
        )


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
