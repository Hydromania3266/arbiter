"""Agent activity tracking — real-time transparency for every decision."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentActivity:
    """Record of a single agent action during a cycle."""

    timestamp: datetime = field(default_factory=datetime.now)
    role: str = ""         # "🔍 Analyst", "🛡️ Risk", "📰 Sentiment", etc.
    action: str = ""       # "analyzing", "deciding", "executing", "reviewing", "learning", "scoring"
    symbol: str = ""
    thinking: str = ""     # Raw LLM reasoning trace
    result: dict = field(default_factory=dict)  # Structured structured result
    raw_llm_output: str = ""  # Raw LLM response before parsing
    duration_ms: float = 0
    status: str = "processing"  # "processing", "done", "skipped", "error"
    error: str = ""
    meta: dict = field(default_factory=dict)  # Extra metadata (confidence, price, etc.)


@dataclass
class CycleSummary:
    """Aggregate summary for one full analysis cycle."""

    cycle_number: int
    start_time: datetime
    symbols_analyzed: list[str]
    trades_executed: int
    activities: list[AgentActivity]
    portfolio_state: dict


class ActivityLog:
    """Thread-safe activity log with filtering and cycle tracking."""

    def __init__(self, max_activities: int = 500) -> None:
        self._max = max_activities
        self._activities: list[AgentActivity] = []
        self._cycles: list[CycleSummary] = []
        self._lock = threading.Lock()
        self._cycle_counter: int = 0

    def add_activity(self, activity: AgentActivity) -> None:
        with self._lock:
            self._activities.append(activity)
            if len(self._activities) > self._max:
                self._activities = self._activities[-self._max:]

    def add_cycle(self, summary: CycleSummary) -> None:
        with self._lock:
            self._cycles.append(summary)
            self._cycle_counter += 1

    def next_cycle_number(self) -> int:
        with self._lock:
            self._cycle_counter += 1
            return self._cycle_counter

    def get_recent(self, n: int = 100) -> list[AgentActivity]:
        with self._lock:
            return list(self._activities[-n:])

    def filter_by_role(self, role: str) -> list[AgentActivity]:
        with self._lock:
            return [a for a in self._activities if a.role == role]

    def filter_by_symbol(self, symbol: str) -> list[AgentActivity]:
        with self._lock:
            return [a for a in self._activities if a.symbol == symbol]

    def get_last_by_role(self, role: str) -> AgentActivity | None:
        with self._lock:
            for a in reversed(self._activities):
                if a.role == role:
                    return a
        return None
