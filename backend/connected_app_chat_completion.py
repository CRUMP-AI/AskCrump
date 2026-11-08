"""Atomic completion of a connected-app chat turn.

The database transaction behind this boundary persists the user/assistant
messages, the durable chat-job response, the content-free completion receipt,
and the terminal turn transition together.  A response-loss readback may
return that exact committed result, but it can never create a second reply.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import hmac
import json
import re
from typing import Protocol
from uuid import UUID, uuid5


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COMPLETION_NAMESPACE = UUID("5085b39b-7ec4-552d-9fc1-ceae9292584c")
_BINDING_VERSION = "connected-operator-chat-completion-v1"
_MAX_TITLE_BYTES = 512
_MAX_JSON_BYTES = 1_048_576


def _uuid(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if canonical != value:
        raise ValueError(f"{name} is invalid")
    return value


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError(f"{name} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} is invalid")
    return parsed.astimezone(UTC)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ValueError("completion content is invalid") from None


def _json_object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"{name} is invalid")
    encoded = _canonical(value)
    if len(encoded) > _MAX_JSON_BYTES:
        raise ValueError(f"{name} is invalid")
    return value  # type: ignore[return-value]


class ConnectedChatCompletionKind(StrEnum):
    DELEGATED = "delegated"
    CLARIFICATION = "clarification"
    PENDING_APPROVAL = "pending_approval"
    SCHEDULE_CREATED = "schedule_created"
    ACTION_TERMINAL = "action_terminal"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedChatCompletionKey:
    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("completion key ID is invalid")
        if not isinstance(self.secret, bytes) or len(self.secret) != 32:
            raise ValueError("completion key must contain exactly 32 bytes")

    @classmethod
    def from_base64(cls, key_id: str, encoded: str) -> ConnectedChatCompletionKey:
        if not isinstance(encoded, str):
            raise ValueError("completion key is invalid")
        try:
            secret = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError):
            raise ValueError("completion key is invalid") from None
        return cls(key_id=key_id, secret=secret)

    def __repr__(self) -> str:
        return f"ConnectedChatCompletionKey(key_id={self.key_id!r}, secret='<redacted>')"

    def __reduce__(self):
        raise TypeError("completion key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedChatCompletionCommand:
    completion_id: str
    owner_id: str
    session_id: str = field(repr=False)
    turn_id: str
    chat_id: str
    message_id: str
    assistant_message_id: str
    claim_token: str = field(repr=False)
    origin_session_binding_sha256: str = field(repr=False)
    request_binding_sha256: str = field(repr=False)
    kind: ConnectedChatCompletionKind
    completion_key_id: str
    response_binding_sha256: str = field(repr=False)
    title: str = field(repr=False)
    user_message: dict[str, object] = field(repr=False)
    assistant_message: dict[str, object] = field(repr=False)
    response_data: dict[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        for name in (
            "completion_id",
            "owner_id",
            "session_id",
            "turn_id",
            "chat_id",
            "message_id",
            "assistant_message_id",
            "claim_token",
        ):
            _uuid(getattr(self, name), name)
        _sha(self.origin_session_binding_sha256, "origin_session_binding_sha256")
        _sha(self.request_binding_sha256, "request_binding_sha256")
        _sha(self.response_binding_sha256, "response_binding_sha256")
        if not isinstance(self.kind, ConnectedChatCompletionKind):
            raise ValueError("completion kind is invalid")
        if not isinstance(self.completion_key_id, str) or not _KEY_ID.fullmatch(
            self.completion_key_id
        ):
            raise ValueError("completion key ID is invalid")
        if (
            not isinstance(self.title, str)
            or not self.title.strip()
            or len(self.title.encode("utf-8")) > _MAX_TITLE_BYTES
        ):
            raise ValueError("title is invalid")
        user = _json_object(self.user_message, "user_message")
        assistant = _json_object(self.assistant_message, "assistant_message")
        response = _json_object(self.response_data, "response_data")
        if user.get("id") != self.message_id or user.get("role") != "user":
            raise ValueError("user_message is invalid")
        if (
            assistant.get("id") != self.assistant_message_id
            or assistant.get("role") != "assistant"
            or (assistant.get("inReplyTo", assistant.get("in_reply_to")) != self.message_id)
        ):
            raise ValueError("assistant_message is invalid")
        response_assistant = response.get("assistantMessage")
        if type(response_assistant) is not dict:
            raise ValueError("response_data is invalid")
        if (
            response_assistant.get("id") != self.assistant_message_id
            or response_assistant.get("inReplyTo", response_assistant.get("in_reply_to"))
            != self.message_id
        ):
            raise ValueError("response_data is invalid")
        expected_completion_id = str(
            uuid5(
                _COMPLETION_NAMESPACE,
                f"{self.owner_id}:{self.turn_id}:{self.kind.value}",
            )
        )
        if self.completion_id != expected_completion_id:
            raise ValueError("completion_id is invalid")

    @classmethod
    def build(
        cls,
        *,
        key: ConnectedChatCompletionKey,
        owner_id: str,
        session_id: str,
        turn_id: str,
        chat_id: str,
        message_id: str,
        assistant_message_id: str,
        claim_token: str,
        origin_session_binding_sha256: str,
        request_binding_sha256: str,
        kind: ConnectedChatCompletionKind,
        title: str,
        user_message: dict[str, object],
        assistant_message: dict[str, object],
        response_data: dict[str, object],
    ) -> ConnectedChatCompletionCommand:
        if type(key) is not ConnectedChatCompletionKey:
            raise ValueError("completion key is invalid")
        for value, name in (
            (owner_id, "owner_id"),
            (session_id, "session_id"),
            (turn_id, "turn_id"),
            (chat_id, "chat_id"),
            (message_id, "message_id"),
            (assistant_message_id, "assistant_message_id"),
            (claim_token, "claim_token"),
        ):
            _uuid(value, name)
        if not isinstance(kind, ConnectedChatCompletionKind):
            raise ValueError("completion kind is invalid")
        completion_id = str(uuid5(_COMPLETION_NAMESPACE, f"{owner_id}:{turn_id}:{kind.value}"))
        binding_material = {
            "version": _BINDING_VERSION,
            "completionId": completion_id,
            "ownerId": owner_id,
            "turnId": turn_id,
            "chatId": chat_id,
            "messageId": message_id,
            "assistantMessageId": assistant_message_id,
            "claimToken": claim_token,
            "originSessionBindingSha256": _sha(
                origin_session_binding_sha256, "origin_session_binding_sha256"
            ),
            "requestBindingSha256": _sha(request_binding_sha256, "request_binding_sha256"),
            "kind": kind.value,
            "keyId": key.key_id,
            "title": title,
            "userMessage": user_message,
            "assistantMessage": assistant_message,
            "responseData": response_data,
        }
        response_binding_sha256 = hmac.new(
            key.secret, _canonical(binding_material), hashlib.sha256
        ).hexdigest()
        return cls(
            completion_id=completion_id,
            owner_id=owner_id,
            session_id=session_id,
            turn_id=turn_id,
            chat_id=chat_id,
            message_id=message_id,
            assistant_message_id=assistant_message_id,
            claim_token=claim_token,
            origin_session_binding_sha256=origin_session_binding_sha256,
            request_binding_sha256=request_binding_sha256,
            kind=kind,
            completion_key_id=key.key_id,
            response_binding_sha256=response_binding_sha256,
            title=title,
            user_message=user_message,
            assistant_message=assistant_message,
            response_data=response_data,
        )

    def __repr__(self) -> str:
        return (
            "ConnectedChatCompletionCommand("
            f"completion_id={self.completion_id!r}, kind={self.kind.value!r}, "
            "content='<redacted>')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedChatCompletion:
    completion_id: str
    kind: ConnectedChatCompletionKind
    response_binding_sha256: str
    resulting_revision: int
    resulting_updated_at: datetime
    completed_at: datetime
    response_data: dict[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        _uuid(self.completion_id, "completion_id")
        if not isinstance(self.kind, ConnectedChatCompletionKind):
            raise ValueError("completion kind is invalid")
        _sha(self.response_binding_sha256, "response_binding_sha256")
        if type(self.resulting_revision) is not int or self.resulting_revision < 1:
            raise ValueError("resulting_revision is invalid")
        if (
            not isinstance(self.resulting_updated_at, datetime)
            or self.resulting_updated_at.tzinfo is None
            or not isinstance(self.completed_at, datetime)
            or self.completed_at.tzinfo is None
        ):
            raise ValueError("completion timestamp is invalid")
        object.__setattr__(self, "resulting_updated_at", self.resulting_updated_at.astimezone(UTC))
        object.__setattr__(self, "completed_at", self.completed_at.astimezone(UTC))
        _json_object(self.response_data, "response_data")

    def __repr__(self) -> str:
        return (
            "ConnectedChatCompletion("
            f"completion_id={self.completion_id!r}, kind={self.kind.value!r}, "
            "response='<redacted>')"
        )


class ConnectedChatCompletionError(RuntimeError):
    _ALLOWED = frozenset(
        {
            "CONNECTED_CHAT_COMPLETION_FAILED",
            "CONNECTED_CHAT_COMPLETION_INVALID",
            "CONNECTED_CHAT_COMPLETION_NOT_FOUND",
        }
    )

    def __init__(self, code: str = "CONNECTED_CHAT_COMPLETION_FAILED") -> None:
        self.code = code if code in self._ALLOWED else "CONNECTED_CHAT_COMPLETION_FAILED"
        super().__init__(self.code)


class ConnectedChatCompletionRPC(Protocol):
    async def rpc(self, name: str, payload: dict[str, object]) -> object: ...


_RESULT_KEYS = frozenset(
    {
        "completion_id",
        "kind",
        "response_binding_sha256",
        "resulting_revision",
        "resulting_updated_at",
        "completed_at",
        "response_data",
    }
)


def _completion(value: object) -> ConnectedChatCompletion:
    if isinstance(value, list):
        if len(value) != 1:
            raise ConnectedChatCompletionError("CONNECTED_CHAT_COMPLETION_INVALID")
        value = value[0]
    if type(value) is not dict or frozenset(value) != _RESULT_KEYS:
        raise ConnectedChatCompletionError("CONNECTED_CHAT_COMPLETION_INVALID")
    try:
        return ConnectedChatCompletion(
            completion_id=_uuid(value["completion_id"], "completion_id"),
            kind=ConnectedChatCompletionKind(value["kind"]),
            response_binding_sha256=_sha(
                value["response_binding_sha256"], "response_binding_sha256"
            ),
            resulting_revision=value["resulting_revision"],
            resulting_updated_at=_time(value["resulting_updated_at"], "resulting_updated_at"),
            completed_at=_time(value["completed_at"], "completed_at"),
            response_data=_json_object(value["response_data"], "response_data"),
        )
    except (TypeError, ValueError):
        raise ConnectedChatCompletionError("CONNECTED_CHAT_COMPLETION_INVALID") from None


def _identity(command: ConnectedChatCompletionCommand) -> dict[str, object]:
    return {
        "p_completion_id": command.completion_id,
        "p_owner_id": command.owner_id,
        "p_session_id": command.session_id,
        "p_turn_id": command.turn_id,
        "p_chat_id": command.chat_id,
        "p_message_id": command.message_id,
        "p_origin_session_binding_sha256": command.origin_session_binding_sha256,
        "p_request_binding_sha256": command.request_binding_sha256,
        "p_kind": command.kind.value,
        "p_completion_key_id": command.completion_key_id,
        "p_response_binding_sha256": command.response_binding_sha256,
    }


class SupabaseConnectedChatCompletionStore:
    """Strict RPC boundary with exact response-loss reconciliation."""

    def __init__(self, rpc: ConnectedChatCompletionRPC) -> None:
        if not callable(getattr(rpc, "rpc", None)):
            raise TypeError("completion RPC is invalid")
        self._rpc = rpc

    @staticmethod
    def _matches(
        command: ConnectedChatCompletionCommand,
        result: ConnectedChatCompletion,
    ) -> bool:
        return (
            result.completion_id == command.completion_id
            and result.kind is command.kind
            and hmac.compare_digest(result.response_binding_sha256, command.response_binding_sha256)
            and result.response_data == command.response_data
        )

    async def read(self, command: ConnectedChatCompletionCommand) -> ConnectedChatCompletion | None:
        if type(command) is not ConnectedChatCompletionCommand:
            raise ConnectedChatCompletionError("CONNECTED_CHAT_COMPLETION_INVALID")
        try:
            value = await self._rpc.rpc(
                "connected_operator_read_chat_completion_v1", _identity(command)
            )
        except Exception:
            raise ConnectedChatCompletionError() from None
        if value is None or value == []:
            return None
        result = _completion(value)
        if not self._matches(command, result):
            raise ConnectedChatCompletionError("CONNECTED_CHAT_COMPLETION_INVALID")
        return result

    async def complete(self, command: ConnectedChatCompletionCommand) -> ConnectedChatCompletion:
        if type(command) is not ConnectedChatCompletionCommand:
            raise ConnectedChatCompletionError("CONNECTED_CHAT_COMPLETION_INVALID")
        payload = {
            **_identity(command),
            "p_assistant_message_id": command.assistant_message_id,
            "p_claim_token": command.claim_token,
            "p_title": command.title,
            "p_user_message": command.user_message,
            "p_assistant_message": command.assistant_message,
            "p_response_data": command.response_data,
        }
        try:
            value = await self._rpc.rpc("connected_operator_complete_chat_v1", payload)
            result = _completion(value)
            if not self._matches(command, result):
                raise ConnectedChatCompletionError("CONNECTED_CHAT_COMPLETION_INVALID")
            return result
        except Exception:
            try:
                recovered = await self.read(command)
            except ConnectedChatCompletionError:
                recovered = None
            if recovered is not None:
                return recovered
            raise ConnectedChatCompletionError() from None
