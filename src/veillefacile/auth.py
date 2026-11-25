import secrets


def valid_key(token: str | None, key: str) -> bool:
    """Constant-time check. Compared as bytes: compare_digest raises TypeError on non-ASCII str."""
    return token is not None and secrets.compare_digest(token.encode(), key.encode())
