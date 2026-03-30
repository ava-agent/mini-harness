"""Safety Layer — command blacklist and loop detection."""

from __future__ import annotations

import json
import re


# Patterns that should never be executed via run_command
BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r">\s*/dev/"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bgit\s+push\s+--force\b"),
    re.compile(r"\bgit\s+push\s+-f\b"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-fd"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r":(){ :|:& };:"),  # fork bomb
]

LOOP_THRESHOLD = 3


class SafetyGuard:
    def __init__(self) -> None:
        self._call_counter: dict[str, int] = {}  # "name|args_hash" -> count

    def check_command(self, command: str) -> tuple[bool, str]:
        """Check if a shell command is safe to execute.

        Returns:
            (True, "") if allowed, (False, reason) if blocked.
        """
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(command):
                return False, f"Blocked: command matches dangerous pattern '{pattern.pattern}'"
        return True, ""

    def check_loop(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """Check if the same tool call is being repeated too many times.

        Returns:
            (True, "") if allowed, (False, reason) if loop detected.
        """
        key = f"{tool_name}|{json.dumps(args, sort_keys=True)}"
        self._call_counter[key] = self._call_counter.get(key, 0) + 1
        count = self._call_counter[key]
        if count >= LOOP_THRESHOLD:
            return False, (
                f"Loop detected: {tool_name} called {count} times with same args. "
                f"Try a different approach."
            )
        return True, ""

    def reset_loop(self) -> None:
        """Reset loop counters. Called when user sends a new message."""
        self._call_counter.clear()
