"""Phase 1 contract for token-aware admission and reconciliation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    request_id: str
    current_usage: int
    limit: int
    retry_after_seconds: int | None = None


class TokenLimiter:
    """Phase 1 stub: establishes the contract and permits every request."""

    def __init__(self, limit: int = 50_000) -> None:
        self.limit = limit

    async def try_reserve(self, tenant_key: str, estimated_tokens: int) -> Decision:
        del tenant_key, estimated_tokens
        return Decision(True, uuid.uuid4().hex, 0, self.limit)

    async def reconcile(self, request_id: str, actual_tokens: int) -> None:
        del request_id, actual_tokens
