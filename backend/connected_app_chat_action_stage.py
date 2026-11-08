"""Atomic chat-plan to connected-action staging adapters.

The generic action-preparation RPC is intentionally insufficient for chat:
the durable chat turn, the settled model plan, the live session, and the new
task grant must advance under one owner lock.  This adapter calls the reviewed
chat wrappers and uses exact idempotent replay only to recover a lost database
response.  It never invokes an external provider.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from .connected_app_action_preparation import (
    ConnectedActionPreparationCommand,
    ConnectedActionPreparationView,
    action_preparation_result_matches,
)
from .connected_app_chat_operator import ConnectedOperatorActionContext
from .connected_app_policy import ConnectedActionPolicy


class ConnectedChatActionStageError(RuntimeError):
    _CODES = frozenset(
        {
            "CONNECTED_CHAT_ACTION_STAGE_FAILED",
            "CONNECTED_CHAT_ACTION_STAGE_INVALID",
            "CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID",
        }
    )

    def __init__(self, code: str) -> None:
        self.code = code if code in self._CODES else "CONNECTED_CHAT_ACTION_STAGE_FAILED"
        super().__init__(self.code)


class ConnectedChatActionRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any: ...


class ConnectedPreparationReadback(Protocol):
    async def readback_action_preparation(
        self,
        *,
        owner_id: str,
        request_id: str,
    ) -> ConnectedActionPreparationView | None: ...


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_INVALID")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_INVALID") from None
    if canonical != value:
        raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_INVALID")
    return value


def _instant(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and 1 <= len(value) <= 64:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ConnectedChatActionStageError(
                "CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID"
            ) from None
    else:
        raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID")
    return result


class SupabaseConnectedChatActionStage:
    """Exact service-role adapter for the two chat action-stage RPCs."""

    def __init__(
        self,
        *,
        database: ConnectedChatActionRPC,
        preparations: ConnectedPreparationReadback,
    ) -> None:
        if not callable(getattr(database, "rpc", None)) or not callable(
            getattr(preparations, "readback_action_preparation", None)
        ):
            raise TypeError("connected chat action-stage dependency is invalid")
        self._database = database
        self._preparations = preparations

    async def _mutate(self, function_name: str, payload: dict[str, object]) -> object:
        """Recover one response loss by replaying the exact database command."""

        for attempt in range(2):
            try:
                return await self._database.rpc(
                    function_name,
                    payload,
                    retry_transient=False,
                )
            except Exception:
                if attempt:
                    break
        raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_FAILED") from None

    async def prepare(
        self,
        *,
        context: ConnectedOperatorActionContext,
        plan_payload_id: str,
        command: ConnectedActionPreparationCommand,
    ) -> ConnectedActionPreparationView:
        if (
            type(context) is not ConnectedOperatorActionContext
            or type(command) is not ConnectedActionPreparationCommand
            or command.owner_id != context.request.owner_id
            or command.session_id != context.request.session_id
            or command.turn_id != context.turn_id
            or command.session_binding_sha256 != context.origin_session_binding_sha256
        ):
            raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_INVALID")
        review = command.review_payload
        payload: dict[str, object] = {
            "p_owner_id": context.request.owner_id,
            "p_session_id": context.request.session_id,
            "p_chat_id": context.request.chat_id,
            "p_message_id": context.request.message_id,
            "p_turn_id": context.turn_id,
            "p_claim_token": context.claim_token,
            "p_origin_session_binding_sha256": context.origin_session_binding_sha256,
            "p_request_binding_sha256": context.request_binding_sha256,
            "p_request_id": command.request_id,
            "p_session_binding_sha256": command.session_binding_sha256,
            "p_command_binding_sha256": command.command_binding_sha256,
            "p_grant_id": command.grant_id,
            "p_action_id": command.action_id,
            "p_task_id": command.task_id,
            "p_connection_id": command.connection_id,
            "p_payload_id": _uuid(plan_payload_id, "plan_payload_id"),
            "p_payload_reference_binding_sha256": command.payload.binding_sha256,
            "p_provider": command.provider.value,
            "p_resource": command.resource.value,
            "p_action": command.action.value,
            "p_authorization_revision": command.authorization_revision,
            "p_authorization_snapshot_sha256": command.authorization_snapshot_sha256,
            "p_granted_actions_sha256": command.granted_actions_sha256,
            "p_granted_scopes_sha256": command.granted_scopes_sha256,
            "p_task_state_revision": command.task_state_revision,
            "p_parameters_payload_id": command.payload.payload_id,
            "p_parameters_reference_binding_sha256": command.payload.binding_sha256,
            "p_parameters_sha256": command.payload.payload_sha256,
            "p_resource_version_sha256": command.resource_version_sha256,
            "p_policy_version": ConnectedActionPolicy.version,
            "p_approval_id": command.approval_id,
            "p_approval_binding_sha256": command.approval_binding_sha256,
            "p_preview_payload_id": None if review is None else review.payload_id,
            "p_preview_reference_binding_sha256": (
                None if review is None else review.binding_sha256
            ),
            "p_preview_sha256": None if review is None else review.payload_sha256,
            "p_requested_at": command.requested_at.isoformat(),
            "p_expires_at": command.expires_at.isoformat(),
        }
        await self._mutate("connected_operator_prepare_chat_action_v1", payload)
        try:
            result = await self._preparations.readback_action_preparation(
                owner_id=command.owner_id,
                request_id=command.request_id,
            )
        except Exception:
            raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_FAILED") from None
        if not action_preparation_result_matches(command, result):
            raise ConnectedChatActionStageError(
                "CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID"
            )
        assert result is not None
        return result

    async def begin_read(
        self,
        *,
        context: ConnectedOperatorActionContext,
        execution_request_id: str,
        preparation: ConnectedActionPreparationView,
    ) -> None:
        if (
            type(context) is not ConnectedOperatorActionContext
            or type(preparation) is not ConnectedActionPreparationView
            or preparation.owner_id != context.request.owner_id
            or preparation.turn_id != context.turn_id
            or preparation.mutates_external_state
        ):
            raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_INVALID")
        execution = _uuid(execution_request_id, "execution_request_id")
        value = await self._mutate(
            "connected_operator_begin_chat_read_v1",
            {
                "p_execution_request_id": execution,
                "p_owner_id": context.request.owner_id,
                "p_session_id": context.request.session_id,
                "p_chat_id": context.request.chat_id,
                "p_message_id": context.request.message_id,
                "p_turn_id": context.turn_id,
                "p_origin_session_binding_sha256": context.origin_session_binding_sha256,
                "p_request_binding_sha256": context.request_binding_sha256,
                "p_claim_token": context.claim_token,
                "p_preparation_request_id": preparation.request_id,
                "p_action_id": preparation.action_id,
                "p_command_binding_sha256": preparation.command_binding_sha256,
            },
        )
        if isinstance(value, list):
            if len(value) != 1:
                raise ConnectedChatActionStageError(
                    "CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID"
                )
            value = value[0]
        if type(value) is not dict or set(value) != {
            "stage",
            "execution_request_id",
            "preparation_request_id",
            "action_id",
            "updated_at",
        }:
            raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID")
        if (
            value["stage"] != "executing"
            or value["execution_request_id"] != execution
            or value["preparation_request_id"] != preparation.request_id
            or value["action_id"] != preparation.action_id
        ):
            raise ConnectedChatActionStageError("CONNECTED_CHAT_ACTION_STAGE_RESULT_INVALID")
        _instant(value["updated_at"])

    async def read_preparation(
        self,
        *,
        owner_id: str,
        request_id: str,
    ) -> ConnectedActionPreparationView | None:
        try:
            return await self._preparations.readback_action_preparation(
                owner_id=_uuid(owner_id, "owner_id"),
                request_id=_uuid(request_id, "request_id"),
            )
        except ConnectedChatActionStageError:
            raise
        except Exception:
            raise ConnectedChatActionStageError(
                "CONNECTED_CHAT_ACTION_STAGE_FAILED"
            ) from None

    def __repr__(self) -> str:
        return "SupabaseConnectedChatActionStage(authority='database', content='<none>')"


__all__ = [
    "ConnectedChatActionRPC",
    "ConnectedChatActionStageError",
    "ConnectedPreparationReadback",
    "SupabaseConnectedChatActionStage",
]
