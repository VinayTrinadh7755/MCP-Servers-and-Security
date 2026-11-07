from __future__ import annotations

import asyncio
import multiprocessing
from pathlib import Path
from queue import Empty

import pytest

from task4.db.connection import init
from task4.limiter import TokenLimiter


def reservation_worker(path: str, result_queue: multiprocessing.Queue) -> None:
    async def run() -> tuple[int, int]:
        limiter = TokenLimiter(limit=50_000, path=Path(path))
        results = await asyncio.gather(
            *(limiter.try_reserve("tenant-a", 1_000) for _ in range(30)),
            return_exceptions=True,
        )
        admitted = sum(
            result.allowed for result in results if not isinstance(result, BaseException)
        )
        errors = sum(isinstance(result, BaseException) for result in results)
        return admitted, errors

    result_queue.put(asyncio.run(run()))


@pytest.mark.asyncio
async def test_two_processes_contend_without_exceeding_cap(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    processes = [
        context.Process(target=reservation_worker, args=(str(path), result_queue))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert not process.is_alive()
        assert process.exitcode == 0
    try:
        results = [result_queue.get(timeout=5) for _ in processes]
    except Empty as exc:
        raise AssertionError("worker did not report its result") from exc
    admitted = sum(result[0] for result in results)
    errors = sum(result[1] for result in results)
    assert admitted == 50
    assert admitted * 1_000 == 50_000
    assert errors == 0
