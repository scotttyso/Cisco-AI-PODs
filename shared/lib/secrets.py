"""Secret resolution by reference.

Inventory YAML never holds secrets; it holds *_pass_ref keys that name an
environment variable (today) or a vault path (phase 2). All access goes through
resolve() so we can swap backends without touching call sites.

Workspace rule codeguard-1-hardcoded-credentials: never log or print resolved
secret values. Callers are expected to pass results into requests/SSH directly.
"""
from __future__ import annotations

import os


class SecretError(RuntimeError):
    pass


def resolve(ref: str) -> str:
    """Resolve a *_pass_ref string to a secret value.

    Supported forms:
      env:VAR_NAME    -> os.environ["VAR_NAME"]
      VAR_NAME        -> os.environ["VAR_NAME"]   (shorthand)

    Phase 2 backends (vault:path/to/secret#field, file:/path) plug in here.
    """
    if not ref or not isinstance(ref, str):
        raise SecretError("empty or non-string secret reference")

    if ref.startswith("env:"):
        var = ref[4:]
    else:
        var = ref

    val = os.environ.get(var)
    if not val:
        raise SecretError(
            f"environment variable {var!r} is not set or empty; "
            "set it before running (or change the *_pass_ref in inventory)"
        )
    return val
