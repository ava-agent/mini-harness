"""SubAgent System — spawn child agents for parallel or isolated tasks.

Claude Code's Agent tool spawns a new Agent with:
  - Its own context window (doesn't pollute parent)
  - A focused prompt (task-specific, not full system prompt)
  - Access to same tools (or a restricted subset)
  - Result returned to parent as a single message

Why SubAgent matters for Landing:
  "Analyze this project" can be decomposed into:
  - SubAgent 1: Analyze directory structure + tech stack
  - SubAgent 2: Analyze git history + contributors
  - SubAgent 3: Read documentation files
  Each runs independently, results merge into the knowledge map.

Design: SubAgents run sequentially (simplest), but the architecture
supports future parallel execution with threading.
"""

from __future__ import annotations

from typing import Any, Optional

from harness.llm import LLMClient
from harness.tools import ToolRegistry
from harness.safety import SafetyGuard


class SubAgent:
    """A lightweight child agent with its own context and focused task."""

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        safety: SafetyGuard,
        name: str = "sub",
        max_iterations: int = 8,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.safety = safety
        self.name = name
        self.max_iterations = max_iterations

    def run(self, task: str, context: str = "") -> str:
        """Execute a focused task and return the result.

        Args:
            task: What the sub-agent should do.
            context: Additional context (e.g., project path, prior findings).

        Returns:
            The sub-agent's final text response.
        """
        system_prompt = (
            f"你是一个专注的子 Agent (名称: {self.name})。\n"
            f"你只需要完成一个具体任务，完成后直接返回结果。\n"
            f"不要做任务范围之外的事情。\n"
        )
        if context:
            system_prompt += f"\n背景信息:\n{context}\n"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        tool_schemas = self.tools.get_schemas()

        for _ in range(self.max_iterations):
            response = self.llm.chat(messages, tools=tool_schemas)

            if not response.tool_calls:
                return response.content or "(no response)"

            # Process tool calls
            import json
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

                # Safety check
                if name == "run_command" and "command" in args:
                    allowed, reason = self.safety.check_command(args["command"])
                    if not allowed:
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": f"[BLOCKED] {reason}"})
                        continue

                result = self.tools.execute(name, args)
                _print_sub(self.name, name, args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        return "(sub-agent reached max iterations)"


class SubAgentManager:
    """Manages sub-agent creation and orchestration."""

    def __init__(self, llm: LLMClient, tools: ToolRegistry, safety: SafetyGuard) -> None:
        self.llm = llm
        self.tools = tools
        self.safety = safety
        self._results: dict[str, str] = {}

    def spawn(self, name: str, task: str, context: str = "") -> str:
        """Spawn a sub-agent, run it, and return the result."""
        _print_spawn(name, task)
        sub = SubAgent(self.llm, self.tools, self.safety, name=name)
        result = sub.run(task, context)
        self._results[name] = result
        _print_done(name, result)
        return result

    def spawn_many(self, tasks: list[dict[str, str]], context: str = "") -> dict[str, str]:
        """Spawn multiple sub-agents sequentially.

        Args:
            tasks: List of {"name": ..., "task": ...} dicts.
            context: Shared context for all sub-agents.

        Returns:
            Dict of name → result.
        """
        results = {}
        for t in tasks:
            results[t["name"]] = self.spawn(t["name"], t["task"], context)
        return results

    def get_results(self) -> dict[str, str]:
        return dict(self._results)


# --- Terminal output ---

def _print_spawn(name: str, task: str) -> None:
    print(f"  \033[95m▶ SubAgent [{name}]: {task[:80]}\033[0m")

def _print_sub(name: str, tool: str, args: dict) -> None:
    args_brief = str(args)[:60]
    print(f"    \033[90m⚙ [{name}] {tool}({args_brief})\033[0m")

def _print_done(name: str, result: str) -> None:
    brief = result[:100].replace("\n", " ")
    print(f"  \033[95m◀ SubAgent [{name}] done: {brief}\033[0m")
