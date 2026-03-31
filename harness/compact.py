"""Context Compact — progressive compression when conversation grows too long.

Claude Code calls this "Compact": when the conversation history approaches the
context window limit, it automatically compresses older messages to free up space.

Three compression stages (applied in order):
  Stage 1: Truncate long tool outputs (keep first/last N lines)
  Stage 2: Summarize old conversation rounds into a brief recap
  Stage 3: Prune redundant exploration (remove superseded tool calls)
"""

from __future__ import annotations

from typing import Any

# Rough estimate: 1 token ≈ 4 chars for mixed CJK/English
CHARS_PER_TOKEN = 4

# Thresholds (in tokens)
DEFAULT_WINDOW = 120000     # GLM-4-flash context window
RESERVED_TOKENS = 8000      # Reserved for system prompt + tools schema
TRUNCATE_THRESHOLD = 0.70   # Start truncating tool outputs at 70%
SUMMARIZE_THRESHOLD = 0.85  # Start summarizing old messages at 85%


class ContextCompactor:
    """Monitors token usage and compresses messages when needed."""

    def __init__(self, window_size: int = DEFAULT_WINDOW) -> None:
        self.window_size = window_size
        self.budget = window_size - RESERVED_TOKENS

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens in message list."""
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        # tool_calls add ~100 tokens each
        tool_calls = sum(
            len(m.get("tool_calls", []))
            for m in messages
            if m.get("role") == "assistant"
        )
        return total_chars // CHARS_PER_TOKEN + tool_calls * 100

    def compact_if_needed(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
        """Check token usage and compress if necessary.

        Returns:
            (messages, was_compacted) — potentially shortened messages and whether compaction occurred.
        """
        tokens = self.estimate_tokens(messages)
        usage_ratio = tokens / self.budget

        if usage_ratio < TRUNCATE_THRESHOLD:
            return messages, False

        compacted = list(messages)  # shallow copy

        # --- Stage 1: Truncate long tool outputs ---
        if usage_ratio >= TRUNCATE_THRESHOLD:
            compacted = self._truncate_tool_outputs(compacted)
            tokens = self.estimate_tokens(compacted)
            usage_ratio = tokens / self.budget

        # --- Stage 2: Summarize old conversation rounds ---
        if usage_ratio >= SUMMARIZE_THRESHOLD:
            compacted = self._summarize_old_rounds(compacted)

        return compacted, True

    def _truncate_tool_outputs(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stage 1: Truncate tool outputs longer than 50 lines."""
        max_lines = 50
        result = []
        for m in messages:
            if m.get("role") == "tool":
                content = m.get("content", "")
                lines = content.split("\n")
                if len(lines) > max_lines:
                    kept = lines[:25] + [f"\n... ({len(lines) - 50} lines truncated) ...\n"] + lines[-25:]
                    m = {**m, "content": "\n".join(kept)}
            result.append(m)
        return result

    def _summarize_old_rounds(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stage 2: Replace old conversation rounds with a brief summary.

        Keeps: system message + last 10 messages.
        Replaces: everything in between with a summary message.
        """
        if len(messages) <= 12:
            return messages

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= 10:
            return messages

        # Keep last 10 non-system messages
        old_msgs = non_system[:-10]
        recent_msgs = non_system[-10:]

        # Build summary of old messages
        summary_parts = []
        for m in old_msgs:
            role = m.get("role", "")
            content = str(m.get("content", ""))[:200]
            if role == "user":
                summary_parts.append(f"- User asked: {content}")
            elif role == "assistant" and content:
                summary_parts.append(f"- Assistant: {content}")
            # Skip tool messages in summary (too verbose)

        summary = (
            "[Context compressed — earlier conversation summary]\n"
            + "\n".join(summary_parts[-15:])  # Keep last 15 items max
        )

        return system_msgs + [{"role": "user", "content": summary}] + recent_msgs
