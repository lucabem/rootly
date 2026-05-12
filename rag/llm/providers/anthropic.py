from __future__ import annotations

import anthropic as _sdk

from ..base import LLMClient, LLMResponse, TextBlock, ToolUseBlock


class AnthropicLLMClient(LLMClient):
    def __init__(self) -> None:
        self._client = _sdk.Anthropic()

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: str | list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system is not None:
            kwargs["system"] = system
        if tools is not None:
            kwargs["tools"] = tools

        resp = self._client.messages.create(**kwargs)

        content: list[TextBlock | ToolUseBlock] = []
        for block in resp.content:
            if block.type == "text":
                content.append(TextBlock(text=block.text))
            elif block.type == "tool_use":
                content.append(ToolUseBlock(id=block.id, name=block.name, input=block.input))

        return LLMResponse(
            content=content,
            stop_reason=resp.stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
