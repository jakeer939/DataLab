"""Backwards-compatible dependency exports.

Older modules imported authentication helpers from this module; keep the
public names available while delegating to the canonical implementation in
``app.security``.
"""
from .security import (  # noqa: F401
    bearer_scheme,
    create_access_token,
    decode_token,
    get_current_user,
    hash_password,
    pwd_context,
    verify_password,
)
