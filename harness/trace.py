"""Execution Trace — full observability for agent actions.

Records every event in the agent's execution for:
  - Debugging: Why did the agent do X? What did it see?
  - Learning: What patterns lead to good/bad outcomes?
  - Auditing: What operations were performed?

Claude Code logs all operations to enable replay and analysis.
DeerFlow uses OpenTelemetry for distributed tracing.

land's trace is a lightweight JSON event log.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Optional


class Event:
    """A single trace event."""

    def __init__(self, event_type: str, data: dict[str, Any]) -> None:
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.now().isoformat()
        self.elapsed_ms: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "type": self.event_type,
            "timestamp": self.timestamp,
            **self.data,
        }
        if self.elapsed_ms is not None:
            d["elapsed_ms"] = round(self.elapsed_ms, 1)
        return d


class Tracer:
    """Records and displays agent execution events."""

    def __init__(self, trace_dir: str = ".land/traces") -> None:
        self.trace_dir = trace_dir
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._events: list[Event] = []
        self._timers: dict[str, float] = {}
        self._stats = {"llm_calls": 0, "tool_calls": 0, "tokens_est": 0, "blocked": 0}

    # --- Recording ---

    def record(self, event_type: str, **data: Any) -> None:
        """Record an event."""
        self._events.append(Event(event_type, data))

    def start_timer(self, name: str) -> None:
        self._timers[name] = time.time()

    def stop_timer(self, name: str) -> Optional[float]:
        start = self._timers.pop(name, None)
        if start is not None:
            return (time.time() - start) * 1000  # ms
        return None

    # --- Convenience methods ---

    def llm_call(self, model: str, messages_count: int, tokens_est: int) -> None:
        self._stats["llm_calls"] += 1
        self._stats["tokens_est"] += tokens_est
        self.record("llm_call", model=model, messages=messages_count, tokens_est=tokens_est)

    def tool_call(self, name: str, args: dict, result_len: int, elapsed_ms: float) -> None:
        self._stats["tool_calls"] += 1
        self.record("tool_call", tool=name, args_brief=str(args)[:100],
                     result_len=result_len, elapsed_ms=round(elapsed_ms, 1))

    def tool_blocked(self, name: str, reason: str) -> None:
        self._stats["blocked"] += 1
        self.record("tool_blocked", tool=name, reason=reason)

    def user_input(self, message: str) -> None:
        self.record("user_input", message=message[:200])

    def agent_response(self, message: str) -> None:
        self.record("agent_response", message=message[:200])

    def compact_triggered(self, before_msgs: int, after_msgs: int) -> None:
        self.record("compact", before=before_msgs, after=after_msgs)

    def error(self, error: str) -> None:
        self.record("error", error=error)

    # --- Output ---

    def summary(self) -> str:
        """Return a brief execution summary."""
        total_time = 0.0
        for e in self._events:
            if e.data.get("elapsed_ms"):
                total_time += e.data["elapsed_ms"]

        lines = [
            f"Session: {self.session_id}",
            f"Events: {len(self._events)}",
            f"LLM calls: {self._stats['llm_calls']}",
            f"Tool calls: {self._stats['tool_calls']}",
            f"Blocked: {self._stats['blocked']}",
            f"Est. tokens: {self._stats['tokens_est']:,}",
            f"Tool time: {total_time:.0f}ms",
        ]
        return "\n".join(lines)

    def timeline(self, last_n: int = 20) -> str:
        """Return a visual timeline of recent events."""
        events = self._events[-last_n:]
        lines = []
        for e in events:
            ts = e.timestamp.split("T")[1][:8]
            icon = _EVENT_ICONS.get(e.event_type, "·")
            detail = _format_event(e)
            lines.append(f"  {ts} {icon} {detail}")
        return "\n".join(lines)

    def save(self) -> Optional[str]:
        """Save trace to JSON file."""
        if not self._events:
            return None
        os.makedirs(self.trace_dir, exist_ok=True)
        path = os.path.join(self.trace_dir, f"{self.session_id}.json")
        data = {
            "session_id": self.session_id,
            "stats": self._stats,
            "events": [e.to_dict() for e in self._events],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path


# --- Formatting ---

_EVENT_ICONS = {
    "user_input": "💬",
    "llm_call": "🧠",
    "tool_call": "⚙️",
    "tool_blocked": "🚫",
    "agent_response": "💡",
    "compact": "📦",
    "error": "❌",
}

def _format_event(e: Event) -> str:
    t = e.event_type
    d = e.data
    if t == "user_input":
        return f"User: {d.get('message', '')[:60]}"
    if t == "llm_call":
        return f"LLM ({d.get('model','')}) msgs={d.get('messages',0)} tokens≈{d.get('tokens_est',0)}"
    if t == "tool_call":
        return f"{d.get('tool','')} → {d.get('result_len',0)} chars ({d.get('elapsed_ms',0):.0f}ms)"
    if t == "tool_blocked":
        return f"BLOCKED {d.get('tool','')}: {d.get('reason','')[:50]}"
    if t == "agent_response":
        return f"Agent: {d.get('message', '')[:60]}"
    if t == "compact":
        return f"Compact: {d.get('before',0)} → {d.get('after',0)} messages"
    if t == "error":
        return f"Error: {d.get('error','')[:60]}"
    return str(d)[:80]
