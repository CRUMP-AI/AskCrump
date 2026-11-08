"""Bounded physical expiry for connected-operator ciphertext.

The provider-neutral payload vault can contain message bodies, recipients, and
calendar details.  Planning envelopes can contain the same information before
an action is staged.  Logical expiry prevents use, but is not erasure.  This
worker invokes one database-authoritative, content-free purge that replaces
expired records with permanent non-content tombstones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


_MAXIMUM = 100


class ConnectedPayloadRetentionError(RuntimeError):
    """Content-free retention failure safe for operational telemetry."""

    _CODES = frozenset(
        {
            "CONNECTED_PAYLOAD_RETENTION_INVALID",
            "CONNECTED_PAYLOAD_RETENTION_UNAVAILABLE",
            "CONNECTED_PAYLOAD_RETENTION_RESPONSE_INVALID",
        }
    )

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = (
            code
            if code in self._CODES
            else "CONNECTED_PAYLOAD_RETENTION_UNAVAILABLE"
        )
        self.retryable = bool(retryable)
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class ConnectedPayloadRetentionResult:
    payloads_purged: int
    plans_purged: int
    loop_envelopes_purged: int

    def __post_init__(self) -> None:
        for value in (
            self.payloads_purged,
            self.plans_purged,
            self.loop_envelopes_purged,
        ):
            if type(value) is not int or value < 0:
                raise ValueError("retention count is invalid")


class ConnectedPayloadRetentionRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class SupabaseConnectedPayloadRetentionPurger:
    """Strict adapter for the atomic bounded ciphertext-expiry RPC."""

    def __init__(self, database: ConnectedPayloadRetentionRPC) -> None:
        if not callable(getattr(database, "rpc", None)):
            raise TypeError("payload-retention RPC boundary is invalid")
        self._database = database

    @staticmethod
    def _maximum(value: int) -> int:
        if type(value) is not int or not 1 <= value <= _MAXIMUM:
            raise ConnectedPayloadRetentionError(
                "CONNECTED_PAYLOAD_RETENTION_INVALID"
            )
        return value

    async def run_bounded(
        self,
        *,
        payload_maximum: int = 32,
        plan_maximum: int = 32,
        loop_maximum: int = 32,
    ) -> ConnectedPayloadRetentionResult:
        payload_limit = self._maximum(payload_maximum)
        plan_limit = self._maximum(plan_maximum)
        loop_limit = self._maximum(loop_maximum)
        try:
            value = await self._database.rpc(
                "connected_app_purge_expired_ciphertext_v1",
                {
                    "p_payload_maximum": payload_limit,
                    "p_plan_maximum": plan_limit,
                    "p_loop_maximum": loop_limit,
                },
                retry_transient=False,
            )
        except ConnectedPayloadRetentionError:
            raise
        except Exception:
            raise ConnectedPayloadRetentionError(
                "CONNECTED_PAYLOAD_RETENTION_UNAVAILABLE", retryable=True
            ) from None
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if type(value) is not dict or set(value) != {
            "payloads_purged",
            "plans_purged",
            "loop_envelopes_purged",
        }:
            raise ConnectedPayloadRetentionError(
                "CONNECTED_PAYLOAD_RETENTION_RESPONSE_INVALID"
            )
        payloads = value["payloads_purged"]
        plans = value["plans_purged"]
        loop_envelopes = value["loop_envelopes_purged"]
        if (
            type(payloads) is not int
            or type(plans) is not int
            or type(loop_envelopes) is not int
            or not 0 <= payloads <= payload_limit
            or not 0 <= plans <= plan_limit
            or not 0 <= loop_envelopes <= loop_limit
        ):
            raise ConnectedPayloadRetentionError(
                "CONNECTED_PAYLOAD_RETENTION_RESPONSE_INVALID"
            )
        return ConnectedPayloadRetentionResult(
            payloads_purged=payloads,
            plans_purged=plans,
            loop_envelopes_purged=loop_envelopes,
        )

    def __repr__(self) -> str:
        return "SupabaseConnectedPayloadRetentionPurger(database='<redacted>')"
