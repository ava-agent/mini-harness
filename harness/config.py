"""Configuration System — project-level rules and harness settings.

Claude Code uses a two-level config:
  1. LAND.md  (human-readable, Markdown, project root) — like CLAUDE.md
  2. .land/settings.json (machine-readable, structured)

LAND.md is injected into the System Prompt so the Agent knows project-specific
rules, coding standards, architecture constraints, and team context.

settings.json controls harness behavior: max iterations, permission mode, etc.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


DEFAULT_SETTINGS = {
    "max_iterations": 15,
    "context_window": 120000,
    "permission_mode": "semi-auto",    # auto / semi-auto / manual
    "memory_token_budget": 2000,
    "output_dir": "output",
}


class ConfigManager:
    """Loads project config from LAND.md and .land/settings.json."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.land_md_path = self.project_root / "LAND.md"
        self.settings_path = self.project_root / ".land" / "settings.json"
        self.settings = self._load_settings()
        self.land_md = self._load_land_md()

    def _load_settings(self) -> dict[str, Any]:
        """Load settings.json, merge with defaults."""
        settings = dict(DEFAULT_SETTINGS)
        if self.settings_path.is_file():
            with open(self.settings_path, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            settings.update(overrides)
        return settings

    def _load_land_md(self) -> str:
        """Load LAND.md content, or return empty string."""
        if self.land_md_path.is_file():
            with open(self.land_md_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        return self.settings.get(key, default)

    def inject_into_prompt(self) -> str:
        """Return LAND.md content formatted for System Prompt injection.

        Extracts and returns the content, truncated to ~2000 chars
        to avoid consuming too much context budget.
        """
        if not self.land_md:
            return ""

        content = self.land_md
        if len(content) > 2000:
            content = content[:2000] + "\n\n... (LAND.md truncated, see full file)"

        return f"## 项目规则 (from LAND.md)\n\n{content}"

    def save_settings(self, overrides: dict[str, Any]) -> None:
        """Save settings to .land/settings.json."""
        self.settings.update(overrides)
        os.makedirs(self.settings_path.parent, exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def init_land_md(self) -> str:
        """Create a template LAND.md if it doesn't exist. Returns the path."""
        if self.land_md_path.exists():
            return str(self.land_md_path)

        template = """\
# Project Rules for land

<!-- land 会读取这个文件并注入到 Agent 的 System Prompt 中 -->
<!-- 写下项目特有的规则、约定和上下文 -->

## Coding Standards
<!-- 例: 语言、框架、代码风格 -->

## Architecture
<!-- 例: 分层结构、核心模块、部署方式 -->

## Rules
<!-- 例: "不要修改 config/ 目录下的文件" -->

## Team Context
<!-- 例: "@张三 负责 order-service" -->
"""
        with open(self.land_md_path, "w", encoding="utf-8") as f:
            f.write(template)
        self.land_md = template
        return str(self.land_md_path)
