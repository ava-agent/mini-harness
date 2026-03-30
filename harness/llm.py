"""LLM Client — wraps OpenAI-compatible API for GLM (ZhipuAI)."""

from __future__ import annotations

import os
from typing import Any, Optional

from openai import OpenAI


class LLMClient:
    def __init__(self) -> None:
        api_key = os.environ.get("GLM_API_KEY", "")
        base_url = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        self.model = os.environ.get("GLM_MODEL", "glm-4-flash")

        if not api_key:
            raise ValueError("GLM_API_KEY environment variable is required")

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
