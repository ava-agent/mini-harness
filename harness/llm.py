"""LLM Client — wraps Volcengine Ark's OpenAI-compatible API."""

from __future__ import annotations

import os
from typing import Any, Optional

from openai import OpenAI


class LLMClient:
    def __init__(self) -> None:
        api_key = os.environ.get("ARK_API_KEY", "")
        base_url = os.environ.get(
            "ARK_BASE_URL",
            "https://ark.cn-beijing.volces.com/api/coding/v3",
        )
        self.model = os.environ.get(
            "ARK_CHAT_MODEL",
            "doubao-seed-2-0-code-preview-260215",
        )

        if not api_key:
            raise ValueError("ARK_API_KEY environment variable is required")

        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> Any:
        """Send messages to LLM and return the response message.

        Args:
            messages: Conversation history in OpenAI format.
            tools: Optional tool schemas in OpenAI function-calling format.

        Returns:
            The response message object from the API.
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message
