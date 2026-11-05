import re
from dataclasses import dataclass
from typing import Any


TOOL_NAME = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    tool_name: str | None = None


def authorize(method: str, params: Any, role: str | None) -> Decision:
    if method == "tools/list":
        return Decision(True, "tool_discovery")

    if method != "tools/call":
        return Decision(False, "unsupported_method")

    if not isinstance(params, dict):
        return Decision(False, "missing_params")

    name = params.get("name")
    if not isinstance(name, str) or TOOL_NAME.fullmatch(name) is None:
        return Decision(False, "invalid_tool_name")

    if name.casefold().startswith("admin_") and role != "admin":
        return Decision(False, "admin_role_required", name)

    return Decision(True, "authorized", name)
