"""Bounded, content-free destinations carried by verification links."""

from __future__ import annotations

from urllib.parse import urlencode


CREATION_INTENTS = frozenset({
    "document",
    "presentation",
    "resume",
    "video",
    "projects",
})
PAID_PLAN_INTENTS = frozenset({"professional", "enterprise"})


def creation_intent(value: str | None) -> str | None:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in CREATION_INTENTS else None


def paid_plan_intent(value: str | None) -> str | None:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in PAID_PLAN_INTENTS else None


def verification_email_url(
    app_url: str,
    token: str,
    *,
    intent: str | None = None,
    plan: str | None = None,
) -> str:
    """Build a verification URL containing only allowlisted navigation context."""
    query: list[tuple[str, str]] = [("token", token)]
    safe_intent = creation_intent(intent)
    safe_plan = paid_plan_intent(plan)
    if safe_intent:
        query.append(("intent", safe_intent))
    if safe_plan:
        query.append(("plan", safe_plan))
    return f"{app_url.rstrip('/')}/api/auth/verify-email?{urlencode(query)}"


def verified_workspace_url(
    app_url: str,
    *,
    intent: str | None = None,
    plan: str | None = None,
) -> str:
    """Return the post-verification workspace URL without granting an entitlement."""
    query: list[tuple[str, str]] = [("verification", "success")]
    safe_intent = creation_intent(intent)
    safe_plan = paid_plan_intent(plan)
    if safe_intent:
        query.append(("intent", safe_intent))
    if safe_plan:
        query.append(("plan", safe_plan))
    return f"{app_url.rstrip('/')}/app?{urlencode(query)}"
