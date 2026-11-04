from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    subject: str
    role: str


TOKEN_ROLES = {
    "token-admin-001": Identity(subject="demo-admin", role="admin"),
    "token-viewer-001": Identity(subject="demo-viewer", role="viewer"),
}


def resolve_identity(authorization: str | None) -> Identity | None:
    if authorization is None:
        return None
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
        return None
    return TOKEN_ROLES.get(parts[1])
