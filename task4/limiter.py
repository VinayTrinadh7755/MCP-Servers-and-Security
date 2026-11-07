"""Atomic SQLite sliding-window token limiter."""

from __future__ import annotations

import uuid
import math
import time
import asyncio
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from task4.db.connection import connect, database_path


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    request_id: str
    current_usage: int
    limit: int
    retry_after_seconds: int | None = None

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.current_usage)


class TokenLimiter:
    """Reserve estimated tokens atomically, then reconcile with actual usage."""

    def __init__(
        self,
        limit: int = 50_000,
        window_ms: int = 60_000,
        path: Path | str | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.limit = limit
        self.window_ms = window_ms
        self.path = Path(path).resolve() if path is not None else database_path()
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        # Avoid burning SQLite busy-timeout intervals for coroutines in this process.
        # BEGIN IMMEDIATE remains the cross-process correctness boundary.
        self._write_lock = asyncio.Lock()

    async def try_reserve(self, tenant_key: str, estimated_tokens: int) -> Decision:
        async with self._write_lock:
            return await self._try_reserve_locked(tenant_key, estimated_tokens)

    async def _try_reserve_locked(
        self, tenant_key: str, estimated_tokens: int
    ) -> Decision:
        if not tenant_key or estimated_tokens <= 0:
            raise ValueError("tenant_key and estimated_tokens must be positive")
        request_id = uuid.uuid4().hex
        now_ms = int(self._clock_ms())
        cutoff_ms = now_ms - self.window_ms
        connection = await connect(self.path)
        try:
            # The up-front write lock makes usage-read plus reservation-insert atomic.
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute("DELETE FROM token_usage WHERE ts_ms <= ?", (cutoff_ms,))
            row = await (
                await connection.execute(
                    "SELECT COALESCE(SUM(tokens), 0), MIN(ts_ms) "
                    "FROM token_usage WHERE tenant_key = ? AND ts_ms > ?",
                    (tenant_key, cutoff_ms),
                )
            ).fetchone()
            current_usage = int(row[0])
            oldest_ms = row[1]
            if current_usage + estimated_tokens > self.limit:
                await connection.commit()
                retry_after = (
                    max(1, math.ceil((int(oldest_ms) + self.window_ms - now_ms) / 1000))
                    if oldest_ms is not None
                    else max(1, math.ceil(self.window_ms / 1000))
                )
                return Decision(
                    False,
                    request_id,
                    current_usage,
                    self.limit,
                    retry_after,
                )
            await connection.execute(
                "INSERT INTO token_usage(request_id, tenant_key, ts_ms, tokens, status) "
                "VALUES (?, ?, ?, ?, 'reserved')",
                (request_id, tenant_key, now_ms, estimated_tokens),
            )
            await connection.commit()
            return Decision(
                True,
                request_id,
                current_usage + estimated_tokens,
                self.limit,
            )
        except BaseException:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def reconcile(self, request_id: str, actual_tokens: int) -> None:
        if actual_tokens < 0:
            raise ValueError("actual_tokens cannot be negative")
        connection = await connect(self.path)
        try:
            cursor = await connection.execute(
                "UPDATE token_usage SET tokens = ?, status = 'reconciled' "
                "WHERE request_id = ? AND status = 'reserved'",
                (actual_tokens, request_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("reservation not found")
            await connection.commit()
        finally:
            await connection.close()

    async def release(self, request_id: str) -> None:
        """Remove a reservation when no provider produced a completion."""

        connection = await connect(self.path)
        try:
            await connection.execute(
                "DELETE FROM token_usage WHERE request_id = ? AND status = 'reserved'",
                (request_id,),
            )
            await connection.commit()
        finally:
            await connection.close()
