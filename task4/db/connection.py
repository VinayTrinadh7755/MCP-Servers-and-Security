"""SQLite connection setup shared by the Task 4 limiter."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import aiosqlite


TASK4_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = TASK4_ROOT / "data" / "usage.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def database_path() -> Path:
    """Return the configured on-disk database path."""

    configured = os.getenv("TASK4_DATABASE_PATH")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DATABASE_PATH


async def connect(path: Path | str | None = None) -> aiosqlite.Connection:
    """Open a configured connection with predictable concurrency behavior."""

    resolved = Path(path).resolve() if path is not None else database_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(resolved)
    try:
        # WAL permits readers while a writer owns the database write lock.
        await connection.execute("PRAGMA journal_mode=WAL")
        # A concurrent writer waits briefly instead of failing immediately.
        await connection.execute("PRAGMA busy_timeout=5000")
        await connection.execute("PRAGMA foreign_keys=ON")
        # Bound retained WAL bytes after checkpoints; active transactions can
        # temporarily exceed this threshold until a checkpoint is possible.
        await connection.execute("PRAGMA journal_size_limit=4194304")
        return connection
    except BaseException:
        await connection.close()
        raise


async def init(path: Path | str | None = None) -> Path:
    """Create or migrate the configured database idempotently."""

    resolved = Path(path).resolve() if path is not None else database_path()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = await connect(resolved)
    try:
        await connection.executescript(schema)
        await connection.commit()
    finally:
        await connection.close()
    return resolved


if __name__ == "__main__":
    print(asyncio.run(init()))
