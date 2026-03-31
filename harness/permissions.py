"""Permission System — Ask/Allow/Deny per-tool authorization.

Claude Code's Layer 3 safety: pattern-based permission checking.
Same tool can be allowed in one context and blocked in another.

Three permission levels:
  ALLOW — auto-approved, no user interaction
  ASK   — requires user confirmation before execution
  DENY  — always blocked, never executed

Decision order: DENY > ALLOW > ASK > default (ASK in semi-auto mode)
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class Decision(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


# Default permission rules
DEFAULT_RULES = {
    "allow": [
        # Read operations are safe
        "read_file:*",
        "list_dir:*",
        "search_code:*",
        "memorize:*",
        # Safe shell commands
        "run_command:git log*",
        "run_command:git status*",
        "run_command:git shortlog*",
        "run_command:git blame*",
        "run_command:git diff*",
        "run_command:gh *",
        "run_command:glab *",
        "run_command:wc *",
        "run_command:tree *",
        "run_command:head *",
        "run_command:tail *",
        "run_command:cat *",
    ],
    "deny": [
        # Destructive operations
        "run_command:rm -rf*",
        "run_command:sudo *",
        "run_command:mkfs*",
        "run_command:shutdown*",
        "run_command:reboot*",
        "run_command:git push --force*",
        "run_command:git push -f*",
        "run_command:git reset --hard*",
        "run_command:git clean -fd*",
        "run_command:chmod 777*",
    ],
    "ask": [
        # Write operations need confirmation
        "write_file:*",
        "run_command:git push*",
        "run_command:git commit*",
    ],
}


class PermissionChecker:
    """Pattern-based permission checker with Allow/Ask/Deny levels."""

    def __init__(self, rules: Optional[dict] = None, mode: str = "semi-auto") -> None:
        """
        Args:
            rules: dict with 'allow', 'deny', 'ask' lists of patterns.
            mode: 'manual' (ask everything), 'semi-auto' (use rules), 'auto' (allow everything).
        """
        rules = rules or DEFAULT_RULES
        self.mode = mode
        self._allow = [self._compile(p) for p in rules.get("allow", [])]
        self._deny = [self._compile(p) for p in rules.get("deny", [])]
        self._ask = [self._compile(p) for p in rules.get("ask", [])]

    def _compile(self, pattern: str) -> re.Pattern:
        """Compile 'tool_name:glob_pattern' to regex."""
        escaped = re.escape(pattern).replace(r"\*", ".*")
        return re.compile(f"^{escaped}$")

    def _match_key(self, tool_name: str, args: dict) -> str:
        """Build a match key from tool name and primary argument."""
        if tool_name == "run_command":
            return f"run_command:{args.get('command', '')}"
        elif tool_name == "write_file":
            return f"write_file:{args.get('path', '')}"
        elif tool_name == "read_file":
            return f"read_file:{args.get('path', '')}"
        else:
            return f"{tool_name}:{str(args)}"

    def check(self, tool_name: str, args: dict) -> tuple[Decision, str]:
        """Check permission for a tool call.

        Returns:
            (Decision, reason) — the decision and an optional explanation.
        """
        if self.mode == "auto":
            return Decision.ALLOW, ""

        key = self._match_key(tool_name, args)

        # Order: DENY > ALLOW > ASK
        for pattern in self._deny:
            if pattern.match(key):
                return Decision.DENY, f"Denied by rule: {pattern.pattern}"

        for pattern in self._allow:
            if pattern.match(key):
                return Decision.ALLOW, ""

        for pattern in self._ask:
            if pattern.match(key):
                return Decision.ASK, f"Requires approval: {key}"

        # Default: ASK in manual/semi-auto, ALLOW in auto
        if self.mode == "manual":
            return Decision.ASK, f"Manual mode: {key}"
        return Decision.ALLOW, ""

    @staticmethod
    def prompt_user(tool_name: str, args: dict) -> bool:
        """Interactive confirmation prompt. Returns True if user approves."""
        args_brief = str(args)[:120]
        print(f"\n  \033[93m⚠ Approve?\033[0m  {tool_name}({args_brief})")
        try:
            choice = input("  [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return choice == "y"
