"""Memory System — JSON file persistence with token-budgeted recall."""

from __future__ import annotations

import json
import os
from datetime import datetime


class MemoryStore:
    def __init__(self, memory_dir: str = "memory", session_id: str = "") -> None:
        self.memory_dir = memory_dir
        os.makedirs(memory_dir, exist_ok=True)

        if session_id:
            self.session_id = session_id
            self.load(session_id)
        else:
            self.session_id = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            self._facts: list[dict] = []

    def add(self, fact: str, source: str = "") -> None:
        """Add a fact to memory."""
        self._facts.append({
            "fact": fact,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        })
        self.save()  # Auto-persist on every add

    def get_all(self) -> list[dict]:
        """Return all stored facts."""
        return list(self._facts)

    def recall(self, token_budget: int = 2000) -> str:
        """Format facts as a string within a token budget.

        Estimates ~4 chars per token. Returns most recent facts first,
        stopping when budget is exhausted.
        """
        if not self._facts:
            return ""

        char_budget = token_budget * 4
        lines: list[str] = []
        used = 0

        # Most recent facts first (more likely to be relevant)
        for entry in reversed(self._facts):
            line = f"- {entry['fact']}"
            if entry.get("source"):
                line += f" (source: {entry['source']})"
            if used + len(line) > char_budget:
                break
            lines.append(line)
            used += len(line)

        if not lines:
            return ""

        return "## 已知事实\n" + "\n".join(lines)

    def save(self) -> None:
        """Persist facts to JSON file."""
        path = os.path.join(self.memory_dir, f"{self.session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"session_id": self.session_id, "facts": self._facts}, f,
                       ensure_ascii=False, indent=2)

    def load(self, session_id: str) -> None:
        """Load facts from an existing session."""
        path = os.path.join(self.memory_dir, f"{session_id}.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._facts = data.get("facts", [])
            self.session_id = session_id
        else:
            self._facts = []

    def list_sessions(self) -> list[str]:
        """List available session IDs."""
        sessions = []
        for f in sorted(os.listdir(self.memory_dir)):
            if f.endswith(".json"):
                sessions.append(f.replace(".json", ""))
        return sessions

    def summary(self) -> str:
        """Return a brief summary for display."""
        return (
            f"Session: {self.session_id}\n"
            f"Facts: {len(self._facts)}\n"
            + ("\n".join(f"  - {e['fact']}" for e in self._facts[-10:]) if self._facts else "  (empty)")
        )
