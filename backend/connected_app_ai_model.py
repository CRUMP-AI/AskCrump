"""Bounded AI adapter for the connected-operator planning boundary.

The language model is deliberately a proposal engine only.  This adapter
binds usage attribution to one command-bound authenticated owner per call, constrains the model call,
and quarantines provider details.  ``ConnectedOperatorPlanner`` still parses
the exact JSON and independently revalidates connection/action authority.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


_MAX_PROMPT_BYTES = 64 * 1024
_MAX_RESPONSE_BYTES = 48 * 1024


def _uuid(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("owner_id must be text")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("owner_id must be a canonical UUID") from None
    if value != canonical:
        raise ValueError("owner_id must be a canonical UUID")
    return value


class ConnectedOperatorTextGateway(Protocol):
    async def gateway_text(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: float,
        user_id: str | None,
        purpose: str,
    ) -> str: ...


class ConnectedOperatorAIModelError(RuntimeError):
    """Content-free model dependency failure."""

    def __init__(self) -> None:
        super().__init__("CONNECTED_OPERATOR_MODEL_FAILED")
        self.code = "CONNECTED_OPERATOR_MODEL_FAILED"


class ConnectedOperatorAIModel:
    """Stateless, per-call owner-bound planning-model implementation."""

    __slots__ = ("_gateway",)

    def __init__(self, gateway: ConnectedOperatorTextGateway) -> None:
        if not callable(getattr(gateway, "gateway_text", None)):
            raise TypeError("connected operator text gateway is invalid")
        self._gateway = gateway

    def __repr__(self) -> str:
        return "ConnectedOperatorAIModel(owner='per-call')"

    async def complete(
        self,
        *,
        owner_id: str,
        system: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> str:
        try:
            owner_id = _uuid(owner_id)
        except (TypeError, ValueError):
            raise ConnectedOperatorAIModelError() from None
        if (
            not isinstance(system, str)
            or not system
            or not isinstance(prompt, str)
            or not prompt
            or len(system.encode("utf-8")) + len(prompt.encode("utf-8")) > _MAX_PROMPT_BYTES
            or type(max_tokens) is not int
            or not 128 <= max_tokens <= 2_000
            or not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 5.0 <= float(timeout_seconds) <= 20.0
        ):
            raise ConnectedOperatorAIModelError()
        try:
            response = await self._gateway.gateway_text(
                system=system,
                prompt=prompt,
                max_tokens=max_tokens,
                timeout_seconds=float(timeout_seconds),
                user_id=owner_id,
                purpose="connected_app_plan",
            )
        except Exception:
            raise ConnectedOperatorAIModelError() from None
        if (
            not isinstance(response, str)
            or not response
            or len(response.encode("utf-8")) > _MAX_RESPONSE_BYTES
        ):
            raise ConnectedOperatorAIModelError()
        return response
