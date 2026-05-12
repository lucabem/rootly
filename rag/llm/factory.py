from __future__ import annotations

import os

from .base import LLMClient


def get_client(provider: str | None = None) -> LLMClient:
    """Return an LLMClient for the requested provider.

    Provider is resolved from the argument, then the LLM_PROVIDER env var,
    then defaults to "anthropic". Valid values: anthropic | openai | bedrock.
    """
    resolved = provider or os.getenv("LLM_PROVIDER", "anthropic")

    if resolved == "anthropic":
        from .providers.anthropic import AnthropicLLMClient
        return AnthropicLLMClient()
    if resolved == "openai":
        from .providers.openai import OpenAILLMClient
        return OpenAILLMClient()
    if resolved == "bedrock":
        from .providers.bedrock import BedrockLLMClient
        return BedrockLLMClient()

    raise ValueError(
        f"Unknown LLM provider {resolved!r}. Valid values: anthropic, openai, bedrock"
    )
