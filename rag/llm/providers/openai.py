from __future__ import annotations

import json
import os

from ..base import LLMClient, LLMResponse, TextBlock, ToolUseBlock


class OpenAILLMClient(LLMClient):
    def __init__(self, api_key: str | None = None) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: str | list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        oai_messages = self._convert_messages(messages, system)
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": oai_messages}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        content: list[TextBlock | ToolUseBlock] = []
        if msg.content:
            content.append(TextBlock(text=msg.content))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                content.append(ToolUseBlock(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))

        stop_reason = "tool_use" if choice.finish_reason == "tool_calls" else "end_turn"
        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )

    # ── message conversion ────────────────────────────────────────────────────

    def _convert_messages(
        self, messages: list[dict], system: str | list[dict] | None
    ) -> list[dict]:
        result: list[dict] = []

        if system is not None:
            text = system if isinstance(system, str) else self._extract_text(system)
            result.append({"role": "system", "content": text})

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                result.append({"role": role, "content": content})
                continue

            if role == "assistant":
                text_blocks = [b for b in content if b.get("type") == "text"]
                tool_blocks = [b for b in content if b.get("type") == "tool_use"]
                oai_msg: dict = {"role": "assistant"}
                if text_blocks:
                    oai_msg["content"] = text_blocks[0]["text"]
                if tool_blocks:
                    oai_msg["tool_calls"] = [
                        {
                            "id": b["id"],
                            "type": "function",
                            "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                        }
                        for b in tool_blocks
                    ]
                result.append(oai_msg)

            elif role == "user":
                tool_results = [b for b in content if b.get("type") == "tool_result"]
                text_blocks = [b for b in content if b.get("type") == "text"]

                if tool_results:
                    for tr in tool_results:
                        result.append({
                            "role": "tool",
                            "tool_call_id": tr["tool_use_id"],
                            "content": tr["content"],
                        })
                else:
                    combined = "\n".join(b.get("text", "") for b in text_blocks)
                    result.append({"role": "user", "content": combined})

        return result

    @staticmethod
    def _extract_text(blocks: list[dict]) -> str:
        return " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]
