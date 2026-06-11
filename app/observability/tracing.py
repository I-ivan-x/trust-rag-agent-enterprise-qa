from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def make_trace_event(step: str, **fields: Any) -> dict[str, Any]:
    return {"step": step, "at": now_iso(), **fields}


@contextmanager
def timed_step(step: str, trace: list[dict[str, Any]], **fields: Any):
    started = time.perf_counter()
    trace.append(make_trace_event(step, status="started", **fields))
    try:
        yield
    except Exception as exc:
        trace.append(
            make_trace_event(
                step,
                status="error",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                error=str(exc),
                **fields,
            )
        )
        raise
    trace.append(
        make_trace_event(
            step,
            status="ok",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            **fields,
        )
    )

