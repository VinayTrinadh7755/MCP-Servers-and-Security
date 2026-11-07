"""Phase 1 provider-router contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    prompt: str
    max_tokens: int


@dataclass(frozen=True, slots=True)
class CompletionResult:
    provider: str
    text: str
    prompt_tokens: int
    completion_tokens: int
    failed_over: bool


class ModelRouter:
    """Phase 1 stub: fixes the interface while always selecting primary."""

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return CompletionResult(
            provider="primary",
            text=f"stub completion: {request.prompt}",
            prompt_tokens=len(request.prompt) // 4 + 1,
            completion_tokens=min(request.max_tokens, 4),
            failed_over=False,
        )
