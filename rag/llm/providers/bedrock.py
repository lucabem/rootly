from __future__ import annotations

import os

from ..base import LLMClient, LLMResponse, TextBlock, ToolUseBlock


class BedrockLLMClient(LLMClient):
    def __init__(self, region_name: str | None = None) -> None:
        import boto3
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=region_name or os.getenv("AWS_REGION", "us-east-1"),
        )

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: str | list[dict] | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "modelId": model,
            "messages": self._convert_messages(messages),
            "inferenceConfig": {"maxTokens": max_tokens},
        }

        if system is not None:
            text = system if isinstance(system, str) else self._extract_text(system)
            kwargs["system"] = [{"text": text}]

        if tools:
            kwargs["toolConfig"] = {"tools": self._convert_tools(tools)}

        resp = self._client.converse(**kwargs)

        output_blocks = resp["output"]["message"]["content"]
        stop_reason = "tool_use" if resp["stopReason"] == "tool_use" else "end_turn"
        usage = resp.get("usage", {})

        content: list[TextBlock | ToolUseBlock] = []
        for block in output_blocks:
            if "text" in block:
                content.append(TextBlock(text=block["text"]))
            elif "toolUse" in block:
                tu = block["toolUse"]
                content.append(ToolUseBlock(
                    id=tu["toolUseId"],
                    name=tu["name"],
                    input=tu.get("input", {}),
                ))

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )

    # ── message conversion ────────────────────────────────────────────────────

    @staticmethod
    def _convert_messages(messages: list[dict]) -> list[dict]:
        result: list[dict] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                result.append({"role": role, "content": [{"text": content}]})
                continue

            bedrock_blocks: list[dict] = []
            for block in content:
                btype = block.get("type")
                if btype == "text":
                    bedrock_blocks.append({"text": block["text"]})
                elif btype == "tool_use":
                    bedrock_blocks.append({
                        "toolUse": {
                            "toolUseId": block["id"],
                            "name": block["name"],
                            "input": block["input"],
                        }
                    })
                elif btype == "tool_result":
                    bedrock_blocks.append({
                        "toolResult": {
                            "toolUseId": block["tool_use_id"],
                            "content": [{"text": str(block["content"])}],
                        }
                    })

            if bedrock_blocks:
                result.append({"role": role, "content": bedrock_blocks})

        return result

    @staticmethod
    def _extract_text(blocks: list[dict]) -> str:
        return " ".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        return [
            {
                "toolSpec": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "inputSchema": {"json": t.get("input_schema", {})},
                }
            }
            for t in tools
        ]
