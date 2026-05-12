from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TextBlock:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


ContentBlock = TextBlock | ToolUseBlock


@dataclass
class LLMResponse:
    content: list[ContentBlock]
    stop_reason: str  # normalized: "end_turn" | "tool_use"
    input_tokens: int = 0
    output_tokens: int = 0


class LLMClient(ABC):
    @abstractmethod
    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: str | list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse: ...

    @staticmethod
    def assistant_content(response: LLMResponse) -> list[dict]:
        """Serialize response content to provider-agnostic dicts for message history."""
        result = []
        for b in response.content:
            if b.type == "text":
                result.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                result.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        return result
