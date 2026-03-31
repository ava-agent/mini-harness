"""Agent Loop — the core think → act → observe cycle.

v0.2: Integrated with Compact, Hooks, Permissions, and Config systems.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from harness.llm import LLMClient
from harness.tools import ToolRegistry
from harness.memory import MemoryStore
from harness.safety import SafetyGuard
from harness.prompt import build_system_prompt
from harness.compact import ContextCompactor
from harness.hooks import HookRegistry, hooks as default_hooks
from harness.permissions import PermissionChecker, Decision
from harness.config import ConfigManager


# ---------------------------------------------------------------------------
# Terminal colors
# ---------------------------------------------------------------------------

class _C:
    GRAY = "\033[90m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Agent:
    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        memory: MemoryStore,
        safety: SafetyGuard,
        project_path: str = "",
        config: Optional[ConfigManager] = None,
        permissions: Optional[PermissionChecker] = None,
        compactor: Optional[ContextCompactor] = None,
        hook_registry: Optional[HookRegistry] = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.memory = memory
        self.safety = safety
        self.project_path = project_path
        self.config = config or ConfigManager(project_path or ".")
        self.permissions = permissions or PermissionChecker(mode=self.config.get("permission_mode", "semi-auto"))
        self.compactor = compactor or ContextCompactor(self.config.get("context_window", 120000))
        self.hooks = hook_registry or default_hooks
        self.max_iterations = self.config.get("max_iterations", 15)
        self.history: list[dict[str, Any]] = []

    def _system_message(self) -> dict[str, str]:
        prompt = build_system_prompt(
            memory_recall=self.memory.recall(),
            project_path=self.project_path,
            project_rules=self.config.inject_into_prompt(),
        )
        return {"role": "system", "content": prompt}

    def run(self, user_message: str) -> str:
        """Execute one turn of the agent loop.

        Flow: Think → [Safety → Permissions → Hooks → Act → Hooks] → Observe → Loop
        """
        self.safety.reset_loop()
        self.history.append({"role": "user", "content": user_message})

        # Build messages: system + history
        messages: list[dict[str, Any]] = [self._system_message()] + self.history

        # --- Context Compact: compress if history is too long ---
        messages, was_compacted = self.compactor.compact_if_needed(messages)
        if was_compacted:
            _print_system("Context compressed to fit window")

        tool_schemas = self.tools.get_schemas()

        for iteration in range(self.max_iterations):
            # --- Think: call LLM ---
            response = self.llm.chat(messages, tools=tool_schemas if tool_schemas else None)

            # --- Case 1: text-only response (done) ---
            if not response.tool_calls:
                content = response.content or ""
                self.history.append({"role": "assistant", "content": content})
                return content

            # --- Case 2: tool calls ---
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)

            for tc in response.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                # --- Layer 2: Safety blacklist ---
                if name == "run_command" and "command" in args:
                    allowed, reason = self.safety.check_command(args["command"])
                    if not allowed:
                        result = f"[BLOCKED] {reason}"
                        _print_tool_blocked(name, args, reason)
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                        continue

                # --- Layer 3: Permission check (Allow/Ask/Deny) ---
                decision, reason = self.permissions.check(name, args)
                if decision == Decision.DENY:
                    result = f"[DENIED] {reason}"
                    _print_tool_blocked(name, args, reason)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue
                if decision == Decision.ASK:
                    if not PermissionChecker.prompt_user(name, args):
                        result = "[CANCELLED] User denied"
                        _print_tool_blocked(name, args, "User denied")
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                        continue

                # --- Layer 4: Loop detection ---
                allowed, reason = self.safety.check_loop(name, args)
                if not allowed:
                    result = f"[LOOP] {reason}"
                    _print_tool_blocked(name, args, reason)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue

                # --- Layer 5: Pre-tool hooks ---
                hook_result = self.hooks.fire_pre_tool_use(name, args)
                if not hook_result.get("allowed", True):
                    result = f"[HOOK] {hook_result.get('reason', 'Blocked by hook')}"
                    _print_tool_blocked(name, args, hook_result.get("reason", ""))
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue
                args = hook_result.get("args", args)

                # --- Execute tool ---
                _print_tool_call(name, args)

                if name == "memorize":
                    self.memory.add(fact=args.get("fact", ""), source=args.get("source", ""))
                    result = f"Memorized: {args.get('fact', '')}"
                else:
                    result = self.tools.execute(name, args)

                _print_tool_result(result)

                # --- Post-tool hooks ---
                self.hooks.fire_post_tool_use(name, args, result)

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # Exhausted iterations
        final = "[Agent reached max iterations without a final response]"
        self.history.append({"role": "assistant", "content": final})
        return final


# ---------------------------------------------------------------------------
# Terminal output helpers
# ---------------------------------------------------------------------------

def _print_tool_call(name: str, args: dict) -> None:
    args_brief = ", ".join(f"{k}={_truncate(str(v), 60)}" for k, v in args.items())
    print(f"  {_C.GRAY}⚙ {name}({args_brief}){_C.RESET}")


def _print_tool_result(result: str) -> None:
    display = _truncate(result, 500)
    lines = display.split("\n")
    for line in lines[:8]:
        print(f"  {_C.CYAN}│ {line}{_C.RESET}")
    if len(lines) > 8:
        print(f"  {_C.CYAN}│ ... ({len(lines) - 8} more lines){_C.RESET}")


def _print_tool_blocked(name: str, args: dict, reason: str) -> None:
    print(f"  {_C.RED}✗ {name} — {reason}{_C.RESET}")


def _print_system(msg: str) -> None:
    print(f"  {_C.YELLOW}⟳ {msg}{_C.RESET}")


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s
