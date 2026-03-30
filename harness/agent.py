"""Agent Loop — the core think → act → observe cycle."""

from __future__ import annotations

import json
from typing import Any

from harness.llm import LLMClient
from harness.tools import ToolRegistry
from harness.memory import MemoryStore
from harness.safety import SafetyGuard
from harness.prompt import build_system_prompt

MAX_ITERATIONS = 15


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
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.memory = memory
        self.safety = safety
        self.project_path = project_path
        self.history: list[dict[str, Any]] = []

    def _system_message(self) -> dict[str, str]:
        prompt = build_system_prompt(
            memory_recall=self.memory.recall(),
            project_path=self.project_path,
        )
        return {"role": "system", "content": prompt}

    def run(self, user_message: str) -> str:
        """Execute one turn of the agent loop.

        Takes a user message, runs the think→act→observe cycle,
        and returns the final text response.
        """
        self.safety.reset_loop()
        self.history.append({"role": "user", "content": user_message})

        # Build messages: system + history
        messages: list[dict[str, Any]] = [self._system_message()] + self.history

        tool_schemas = self.tools.get_schemas()

        for iteration in range(MAX_ITERATIONS):
            # --- Think: call LLM ---
            response = self.llm.chat(messages, tools=tool_schemas if tool_schemas else None)

            # --- Case 1: text-only response (done) ---
            if not response.tool_calls:
                content = response.content or ""
                self.history.append({"role": "assistant", "content": content})
                return content

            # --- Case 2: tool calls ---
            # Append the assistant message with tool_calls
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

                # --- Safety check: commands ---
                if name == "run_command" and "command" in args:
                    allowed, reason = self.safety.check_command(args["command"])
                    if not allowed:
                        result = f"[BLOCKED] {reason}"
                        _print_tool_blocked(name, args, reason)
                        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                        continue

                # --- Safety check: loop detection ---
                allowed, reason = self.safety.check_loop(name, args)
                if not allowed:
                    result = f"[LOOP] {reason}"
                    _print_tool_blocked(name, args, reason)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    continue

                # --- Execute tool ---
                _print_tool_call(name, args)

                # Special handling: memorize goes to MemoryStore
                if name == "memorize":
                    self.memory.add(
                        fact=args.get("fact", ""),
                        source=args.get("source", ""),
                    )
                    result = f"Memorized: {args.get('fact', '')}"
                else:
                    result = self.tools.execute(name, args)

                _print_tool_result(result)

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


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s
