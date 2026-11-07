"""The only client-visible error format used by Task 4."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi.responses import JSONResponse


@dataclass(frozen=True, slots=True)
class GatewayError:
    code: str
    message: str
    request_id: str


def error_response(
    *, code: str, message: str, request_id: str, status_code: int
) -> JSONResponse:
    return JSONResponse(
        {"error": asdict(GatewayError(code, message, request_id))},
        status_code=status_code,
        headers={"x-request-id": request_id},
    )
