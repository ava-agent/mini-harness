"""Tool Registry — @tool decorator, schema generation, and 6 built-in tools."""

from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
from typing import Any, Callable, get_type_hints


# ---------------------------------------------------------------------------
# Tool decorator and registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}  # name -> {func, description, schema}

    def register(self, description: str) -> Callable:
        """Decorator to register a function as a tool."""
        def decorator(func: Callable) -> Callable:
            hints = get_type_hints(func)
            params = inspect.signature(func).parameters
            properties: dict[str, Any] = {}
            required: list[str] = []

            for name, param in params.items():
                hint = hints.get(name, str)
                prop: dict[str, Any] = {"type": _python_type_to_json(hint)}
                # Extract per-param description from docstring
                doc_desc = _extract_param_doc(func.__doc__ or "", name)
                if doc_desc:
                    prop["description"] = doc_desc
                properties[name] = prop
                if param.default is inspect.Parameter.empty:
                    required.append(name)

            schema = {
                "type": "function",
                "function": {
                    "name": func.__name__,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
            self._tools[func.__name__] = {
                "func": func,
                "description": description,
                "schema": schema,
            }
            return func
        return decorator

    def get_schemas(self) -> list[dict]:
        """Return all tool schemas in OpenAI function-calling format."""
        return [t["schema"] for t in self._tools.values()]

    def execute(self, name: str, args: dict) -> str:
        """Execute a tool by name and return result as string."""
        if name not in self._tools:
            return f"Error: unknown tool '{name}'"
        try:
            result = self._tools[name]["func"](**args)
            return str(result)
        except Exception as e:
            return f"Error executing {name}: {e}"

    def names(self) -> list[str]:
        return list(self._tools.keys())


def _python_type_to_json(hint: type) -> str:
    mapping = {str: "string", int: "integer", float: "number", bool: "boolean"}
    return mapping.get(hint, "string")


def _extract_param_doc(docstring: str, param_name: str) -> str:
    """Extract param description from 'param: description' style docstring."""
    for line in docstring.split("\n"):
        stripped = line.strip()
        if stripped.startswith(f"{param_name}:"):
            return stripped[len(param_name) + 1:].strip()
    return ""


# ---------------------------------------------------------------------------
# Global registry instance
# ---------------------------------------------------------------------------

registry = ToolRegistry()
tool = registry.register  # shorthand: @tool(description="...")


# ---------------------------------------------------------------------------
# Built-in tools
# ---------------------------------------------------------------------------

@tool(description="读取文件内容，返回带行号的文本")
def read_file(path: str, limit: int = 200) -> str:
    """path: 文件的绝对或相对路径
    limit: 最多读取的行数，默认 200"""
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Error: file not found: {path}"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    total = len(lines)
    lines = lines[:limit]
    numbered = [f"{i + 1:>5} | {line.rstrip()}" for i, line in enumerate(lines)]
    header = f"[{path}] ({total} lines, showing {len(lines)})"
    return header + "\n" + "\n".join(numbered)


@tool(description="列出目录结构，返回树状格式")
def list_dir(path: str, depth: int = 2) -> str:
    """path: 目录路径
    depth: 递归深度，默认 2"""
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return f"Error: directory not found: {path}"
    lines: list[str] = []
    _walk_tree(path, "", depth, lines, max_entries=200)
    return "\n".join(lines) if lines else "(empty directory)"


def _walk_tree(dir_path: str, prefix: str, depth: int, lines: list[str], max_entries: int) -> None:
    if depth < 0 or len(lines) >= max_entries:
        return
    try:
        entries = sorted(os.listdir(dir_path))
    except PermissionError:
        lines.append(f"{prefix}[permission denied]")
        return
    # Filter hidden files
    entries = [e for e in entries if not e.startswith(".")]
    dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e))]
    files = [e for e in entries if not os.path.isdir(os.path.join(dir_path, e))]
    for f in files:
        if len(lines) >= max_entries:
            lines.append(f"{prefix}... (truncated)")
            return
        lines.append(f"{prefix}{f}")
    for d in dirs:
        if len(lines) >= max_entries:
            lines.append(f"{prefix}... (truncated)")
            return
        lines.append(f"{prefix}{d}/")
        _walk_tree(os.path.join(dir_path, d), prefix + "  ", depth - 1, lines, max_entries)


@tool(description="在代码中搜索模式（正则），返回匹配行")
def search_code(pattern: str, path: str = ".", file_type: str = "") -> str:
    """pattern: 搜索的正则模式
    path: 搜索的根目录，默认当前目录
    file_type: 限定文件类型，如 py, java, go"""
    path = os.path.expanduser(path)
    # Prefer ripgrep, fallback to grep
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "-n", "--max-count=50", pattern, path]
        if file_type:
            cmd.extend(["-t", file_type])
    else:
        cmd = ["grep", "-rn", "--max-count=50", pattern, path]
        if file_type:
            cmd.extend(["--include", f"*.{file_type}"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip()
        return output if output else "(no matches found)"
    except subprocess.TimeoutExpired:
        return "Error: search timed out (15s)"
    except FileNotFoundError:
        return "Error: neither rg nor grep found on system"


@tool(description="执行 shell 命令（可调用 git/gh/glab/feishu-cli 等系统工具）")
def run_command(command: str) -> str:
    """command: 要执行的 shell 命令"""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr.strip():
            output += f"\n[stderr] {result.stderr.strip()}"
        if result.returncode != 0 and not output:
            output = f"[exit code {result.returncode}] {result.stderr.strip()}"
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out (30s)"


@tool(description="写入文件（自动创建父目录）")
def write_file(path: str, content: str) -> str:
    """path: 文件路径
    content: 要写入的内容"""
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Written {len(content)} chars to {path}"


# memorize is a placeholder — wired to MemoryStore in agent.py
@tool(description="记住一个重要发现（跨会话持久化）")
def memorize(fact: str, source: str = "") -> str:
    """fact: 要记住的事实
    source: 信息来源（文件路径、命令等）"""
    # Actual persistence handled by Agent.run() which intercepts this call
    return f"Memorized: {fact}"
