from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LLMUsageTotals:
    answer_calls: int = 0
    rewrite_calls: int = 0
    other_calls: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    usage_reported: bool = False

    @property
    def total_calls(self) -> int:
        return self.answer_calls + self.rewrite_calls + self.other_calls


class LLMUsageTracker:
    """Process-local accounting of real LLM calls and (optional) token usage.

    Mock clients never record here, so a real run with zero calls is visible as
    zero, and we never claim a real LLM eval that did not actually call the API.
    """

    def __init__(self) -> None:
        self.totals = LLMUsageTotals()

    def reset(self) -> None:
        self.totals = LLMUsageTotals()

    def snapshot(self) -> tuple[int, int]:
        return (self.totals.answer_calls, self.totals.rewrite_calls)

    def record(self, purpose: str, usage: dict[str, Any] | None) -> None:
        if purpose == "rewrite":
            self.totals.rewrite_calls += 1
        elif purpose == "answer":
            self.totals.answer_calls += 1
        else:
            self.totals.other_calls += 1
        if not usage:
            return
        self.totals.usage_reported = True
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(field)
            if isinstance(value, int):
                current = getattr(self.totals, field) or 0
                setattr(self.totals, field, current + value)


_TRACKER = LLMUsageTracker()


def get_usage_tracker() -> LLMUsageTracker:
    return _TRACKER
