"""
Stage timing for a WebSocket session.

Prints one ``[TIMING]`` line per pipeline stage (and per research model) as it
finishes, plus a summary line once the first synthesis draft is sent, so the
Railway log shows where a session's wall-clock time went.

Time spent waiting on the user (prompt review, dialogue turns) is never inside
a timed stage: create the timer once research starts.
"""

import time
from contextlib import asynccontextmanager
from typing import Awaitable, List, Tuple, TypeVar

T = TypeVar("T")


class StageTimer:
    def __init__(self) -> None:
        self._start = time.perf_counter()
        self.stages: List[Tuple[str, float]] = []

    def _record(self, name: str, seconds: float, failed: bool = False) -> None:
        self.stages.append((name, seconds))
        suffix = " (failed)" if failed else ""
        print(f"[TIMING] {name} {seconds:.1f}s{suffix}", flush=True)

    @asynccontextmanager
    async def stage(self, name: str):
        """Time the enclosed block. Records the time even if the block raises."""
        t0 = time.perf_counter()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            self._record(name, time.perf_counter() - t0, failed)

    async def timed(self, name: str, awaitable: Awaitable[T]) -> T:
        """Await ``awaitable`` inside a stage — for per-model times in a gather."""
        async with self.stage(name):
            return await awaitable

    def elapsed(self) -> float:
        return time.perf_counter() - self._start

    def summary(self, label: str = "first_draft") -> str:
        """One line: elapsed since the timer started, then every stage so far."""
        parts = " ".join(f"{name}={secs:.1f}s" for name, secs in self.stages)
        return f"[TIMING] {label} total={self.elapsed():.1f}s | {parts}"
