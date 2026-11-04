import httpx
import pytest

from task2.gateway.upstream import UpstreamClient, UpstreamFailure


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body"),
    [(500, b"provider exploded"), (200, b"not-json"), (200, b"[]")],
)
async def test_collapses_bad_downstream_responses(status: int, body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    upstream = UpstreamClient("http://downstream")
    await upstream.close()
    upstream._client = httpx.AsyncClient(
        base_url="http://downstream", transport=httpx.MockTransport(handler)
    )

    try:
        with pytest.raises(UpstreamFailure):
            await upstream.forward(b"{}", "application/json")
    finally:
        await upstream.close()
