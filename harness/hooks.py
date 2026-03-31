"""Hooks System — lifecycle event intercepts for Agent execution.

Claude Code uses hooks as the 5th layer of safety defense-in-depth:
  Layer 1: System Prompt constraints
  Layer 2: Command blacklist (safety.py)
  Layer 3: Permission system (permissions.py)
  Layer 4: Loop detection (safety.py)
  Layer 5: Hooks (this file) — arbitrary pre/post logic

Hook events:
  - pre_tool_use:  Before a tool executes. Can block or modify params.
  - post_tool_use: After a tool executes. Can inspect results.
  - session_start: When a new session begins.
  - session_end:   When session ends (quit/crash).
  - on_error:      When any error occurs during execution.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Type aliases for hook handlers
PreToolHandler = Callable[[str, dict], dict]   # (tool_name, args) -> {allowed, reason?, args?}
PostToolHandler = Callable[[str, dict, str], None]  # (tool_name, args, result) -> None
SessionHandler = Callable[[], None]
ErrorHandler = Callable[[Exception], None]


class HookRegistry:
    """Registry for lifecycle hooks. Handlers are called in registration order."""

    def __init__(self) -> None:
        self._pre_tool: list[PreToolHandler] = []
        self._post_tool: list[PostToolHandler] = []
        self._session_start: list[SessionHandler] = []
        self._session_end: list[SessionHandler] = []
        self._on_error: list[ErrorHandler] = []

    # --- Registration ---

    def pre_tool_use(self, handler: PreToolHandler) -> PreToolHandler:
        """Register a pre-tool-use hook. Can be used as decorator."""
        self._pre_tool.append(handler)
        return handler

    def post_tool_use(self, handler: PostToolHandler) -> PostToolHandler:
        """Register a post-tool-use hook. Can be used as decorator."""
        self._post_tool.append(handler)
        return handler

    def on_session_start(self, handler: SessionHandler) -> SessionHandler:
        self._session_start.append(handler)
        return handler

    def on_session_end(self, handler: SessionHandler) -> SessionHandler:
        self._session_end.append(handler)
        return handler

    def on_error(self, handler: ErrorHandler) -> ErrorHandler:
        self._on_error.append(handler)
        return handler

    # --- Firing ---

    def fire_pre_tool_use(self, tool_name: str, args: dict) -> dict:
        """Fire all pre-tool-use hooks. Returns {allowed, reason, args}.

        If any handler returns allowed=False, execution is blocked.
        Handlers can modify args by returning a new args dict.
        """
        current_args = dict(args)
        for handler in self._pre_tool:
            try:
                result = handler(tool_name, current_args)
                if not result.get("allowed", True):
                    return {"allowed": False, "reason": result.get("reason", "Blocked by hook")}
                if "args" in result:
                    current_args = result["args"]
            except Exception as e:
                logger.warning(f"Hook error in pre_tool_use: {e}")
        return {"allowed": True, "args": current_args}

    def fire_post_tool_use(self, tool_name: str, args: dict, result: str) -> None:
        """Fire all post-tool-use hooks (informational, can't block)."""
        for handler in self._post_tool:
            try:
                handler(tool_name, args, result)
            except Exception as e:
                logger.warning(f"Hook error in post_tool_use: {e}")

    def fire_session_start(self) -> None:
        for handler in self._session_start:
            try:
                handler()
            except Exception as e:
                logger.warning(f"Hook error in session_start: {e}")

    def fire_session_end(self) -> None:
        for handler in self._session_end:
            try:
                handler()
            except Exception as e:
                logger.warning(f"Hook error in session_end: {e}")

    def fire_error(self, error: Exception) -> None:
        for handler in self._on_error:
            try:
                handler(error)
            except Exception:
                pass  # Don't let error handlers cause more errors


# --- Global registry ---
hooks = HookRegistry()


# --- Built-in hooks ---

@hooks.post_tool_use
def audit_log(tool_name: str, args: dict, result: str) -> None:
    """Log every tool call for audit trail."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    args_brief = str(args)[:100]
    result_brief = result[:80].replace("\n", " ")
    logger.debug(f"[{timestamp}] {tool_name}({args_brief}) → {result_brief}")
