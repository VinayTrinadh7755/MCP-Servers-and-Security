import pytest

from task2.gateway.auth import resolve_identity
from task2.gateway.policy import authorize


def test_resolves_only_exact_bearer_credentials() -> None:
    assert resolve_identity("Bearer token-admin-001").role == "admin"
    assert resolve_identity("Bearer token-viewer-001").role == "viewer"
    assert resolve_identity(None) is None
    assert resolve_identity("bearer token-admin-001").role == "admin"
    assert resolve_identity("Bearer unknown") is None
    assert resolve_identity("Bearer  token-admin-001") is None


@pytest.mark.parametrize("role", [None, "viewer"])
def test_non_admin_cannot_call_privileged_tool(role: str | None) -> None:
    decision = authorize("tools/call", {"name": "admin_reset_key"}, role)
    assert decision.allowed is False
    assert decision.reason == "admin_role_required"


def test_admin_can_call_privileged_tool() -> None:
    assert authorize("tools/call", {"name": "admin_reset_key"}, "admin").allowed is True


def test_unknown_method_fails_closed() -> None:
    decision = authorize("resources/list", None, "admin")
    assert decision.allowed is False
    assert decision.reason == "unsupported_method"


@pytest.mark.parametrize("role", [None, "viewer", "admin"])
def test_ordinary_tools_and_listing_are_allowed(role: str | None) -> None:
    assert authorize("tools/list", None, role).allowed is True
    assert authorize("tools/call", {"name": "search_orders"}, role).allowed is True


@pytest.mark.parametrize(
    "params",
    [None, {}, {"name": []}, {"name": {}}, {"name": " admin_reset_key"}, {"name": "аdmin_reset_key"}],
)
def test_malformed_or_ambiguous_tool_names_fail_closed(params: object) -> None:
    assert authorize("tools/call", params, "viewer").allowed is False


def test_tool_name_length_is_bounded() -> None:
    assert authorize("tools/call", {"name": "x" * 128}, "viewer").allowed is True
    assert authorize("tools/call", {"name": "x" * 129}, "viewer").allowed is False
