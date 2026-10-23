"""Shared server-side gate for paid Ask Crump tools.

The browser may hide paid controls, but authorization is based only on the
server-managed account and billing fields that :func:`tier_name` validates.
Safe access to previously owned results is intentionally handled by each route
instead of being blocked wholesale when an entitlement ends.
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from .auth_service import paid_feature_required_response, paid_tools_entitled


def has_paid_tool_access(user: dict[str, Any]) -> bool:
    """Return whether *user* currently has a trusted advanced-tool entitlement."""
    return paid_tools_entitled(user)


def paid_tool_required(
    user: dict[str, Any],
    *,
    label: str = "This tool",
) -> JSONResponse | None:
    """Return a consistent paywall response, or ``None`` when access is allowed."""
    if has_paid_tool_access(user):
        return None
    return paid_feature_required_response(label, user)
