"""Content-free binding for an ordinary-language connected-app chat turn.

The chat message itself never enters the control plane.  A server-held HMAC
key binds the exact owner, authenticated session, conversation, message,
attachment order, and time zone before a planner or provider can run.  The
database sees only canonical UUIDs and opaque keyed commitments.
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
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_MESSAGE_BYTES = 100_000
_MAX_ATTACHMENTS = 10
_BINDING_VERSION = "connected-chat-request-binding-v1"
_SESSION_VERSION = "connected-chat-origin-session-v1"


def _uuid(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{name} is invalid") from None
    if str(parsed) != value:
        raise ValueError(f"{name} is invalid")
    return value


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} is invalid")
    return parsed.astimezone(UTC)


def _canonical(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedChatBindingKey:
    """Dedicated secret used only for chat/session commitments."""

    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not _KEY_ID.fullmatch(self.key_id):
            raise ValueError("connected chat binding key ID is invalid")
        if not isinstance(self.secret, bytes) or len(self.secret) != 32:
            raise ValueError("connected chat binding key must contain exactly 32 bytes")

    @classmethod
    def from_base64(cls, key_id: str, encoded: str) -> ConnectedChatBindingKey:
        if not isinstance(encoded, str):
            raise ValueError("connected chat binding key is invalid")
        try:
            secret = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise ValueError("connected chat binding key is invalid") from None
        return cls(key_id=key_id, secret=secret)

    def __repr__(self) -> str:
        return f"ConnectedChatBindingKey(key_id={self.key_id!r}, secret='<redacted>')"

    def __reduce__(self):
        raise TypeError("connected chat binding key cannot be serialized")


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedChatRequestMaterial:
    owner_id: str
    session_id: str = field(repr=False)
    chat_id: str
    message_id: str
    message: str = field(repr=False)
    attachment_ids: tuple[str, ...] = field(default=(), repr=False)
    time_zone: str = "UTC"

    def __post_init__(self) -> None:
        _uuid(self.owner_id, "owner_id")
        _uuid(self.session_id, "session_id")
        _uuid(self.chat_id, "chat_id")
        _uuid(self.message_id, "message_id")
        if not isinstance(self.message, str):
            raise ValueError("message is invalid")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in self.message):
            raise ValueError("message is invalid")
        if len(self.message.encode("utf-8")) > _MAX_MESSAGE_BYTES:
            raise ValueError("message is invalid")
        if (
            not isinstance(self.attachment_ids, tuple)
            or len(self.attachment_ids) > _MAX_ATTACHMENTS
            or len(set(self.attachment_ids)) != len(self.attachment_ids)
        ):
            raise ValueError("attachment_ids is invalid")
        for attachment_id in self.attachment_ids:
            _uuid(attachment_id, "attachment_id")
        if not isinstance(self.time_zone, str) or not 1 <= len(self.time_zone) <= 100:
            raise ValueError("time_zone is invalid")
        try:
            ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("time_zone is invalid") from None

    def session_binding_sha256(self, key: ConnectedChatBindingKey) -> str:
        if type(key) is not ConnectedChatBindingKey:
            raise ValueError("connected chat binding key is invalid")
        payload = _canonical(
            {
                "version": _SESSION_VERSION,
                "keyId": key.key_id,
                "ownerId": self.owner_id,
                "sessionId": self.session_id,
            }
        )
        return hmac.new(key.secret, payload, hashlib.sha256).hexdigest()

    def request_binding_sha256(self, key: ConnectedChatBindingKey) -> str:
        if type(key) is not ConnectedChatBindingKey:
            raise ValueError("connected chat binding key is invalid")
        payload = _canonical(
            {
                "version": _BINDING_VERSION,
                "keyId": key.key_id,
                "ownerId": self.owner_id,
                "chatId": self.chat_id,
                "messageId": self.message_id,
                "message": self.message,
                "attachmentIds": list(self.attachment_ids),
                "timeZone": self.time_zone,
            }
        )
        return hmac.new(key.secret, payload, hashlib.sha256).hexdigest()

    def command(self, key: ConnectedChatBindingKey) -> ConnectedChatTurnClaimCommand:
        return ConnectedChatTurnClaimCommand(
            owner_id=self.owner_id,
            chat_id=self.chat_id,
            message_id=self.message_id,
            origin_session_binding_sha256=self.session_binding_sha256(key),
            request_binding_sha256=self.request_binding_sha256(key),
        )

    def __repr__(self) -> str:
        return (
            "ConnectedChatRequestMaterial("
            f"owner_id={self.owner_id!r}, chat_id={self.chat_id!r}, "
            f"message_id={self.message_id!r}, content='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class ConnectedChatTurnClaimCommand:
    owner_id: str
    chat_id: str
    message_id: str
    origin_session_binding_sha256: str
    request_binding_sha256: str

    def __post_init__(self) -> None:
        _uuid(self.owner_id, "owner_id")
        _uuid(self.chat_id, "chat_id")
        _uuid(self.message_id, "message_id")
        _sha(self.origin_session_binding_sha256, "origin_session_binding_sha256")
        _sha(self.request_binding_sha256, "request_binding_sha256")


class ConnectedChatTurnState(StrEnum):
    CLAIMED = "claimed"
    BUSY = "busy"
    COMPLETED = "completed"


class ConnectedChatTurnStage(StrEnum):
    CLAIMED = "claimed"
    PLANNING = "planning"
    PLANNED = "planned"
    PREPARED = "prepared"
    EXECUTING = "executing"
    TERMINAL = "terminal"
    EFFECT_UNKNOWN = "effect_unknown"


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedChatTurnClaim:
    state: ConnectedChatTurnState
    turn_id: str
    stage: ConnectedChatTurnStage
    claim_token: str | None
    response_data: dict[str, object] | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.state, ConnectedChatTurnState):
            raise ValueError("chat turn state is invalid")
        _uuid(self.turn_id, "turn_id")
        if not isinstance(self.stage, ConnectedChatTurnStage):
            raise ValueError("chat turn stage is invalid")
        if self.claim_token is not None:
            _uuid(self.claim_token, "claim_token")
        if self.state is ConnectedChatTurnState.CLAIMED and self.claim_token is None:
            raise ValueError("claimed chat turn is missing its claim token")
        if self.state is not ConnectedChatTurnState.CLAIMED and self.claim_token is not None:
            raise ValueError("unclaimed chat turn exposes a claim token")
        if self.response_data is not None and not isinstance(self.response_data, dict):
            raise ValueError("chat turn response is invalid")
        if self.state is ConnectedChatTurnState.COMPLETED and self.response_data is None:
            raise ValueError("completed chat turn is missing its response")
        if self.state is not ConnectedChatTurnState.COMPLETED and self.response_data is not None:
            raise ValueError("unfinished chat turn exposes a response")
        if not isinstance(self.updated_at, datetime) or self.updated_at.tzinfo is None:
            raise ValueError("updated_at is invalid")
        object.__setattr__(self, "updated_at", self.updated_at.astimezone(UTC))

    def __repr__(self) -> str:
        return (
            f"ConnectedChatTurnClaim(state={self.state.value!r}, "
            f"turn_id={self.turn_id!r}, stage={self.stage.value!r}, "
            "response='<redacted>')"
        )


class ConnectedChatTurnError(RuntimeError):
    def __init__(self, code: str = "CONNECTED_CHAT_TURN_FAILED") -> None:
        self.code = (
            code
            if code
            in {
                "CONNECTED_CHAT_TURN_FAILED",
                "CONNECTED_CHAT_TURN_INVALID",
                "CONNECTED_CHAT_TURN_BUSY",
            }
            else "CONNECTED_CHAT_TURN_FAILED"
        )
        super().__init__(self.code)


class ConnectedChatTurnRPC(Protocol):
    async def rpc(self, name: str, payload: dict[str, object]) -> object: ...


_CLAIM_KEYS = frozenset(
    {"job_state", "turn_id", "stage", "claim_token", "response_data", "updated_at"}
)


class SupabaseConnectedChatTurnStore:
    """Strict service-role adapter for the atomic chat-turn claim RPC."""

    def __init__(self, client: ConnectedChatTurnRPC) -> None:
        self._client = client

    async def claim(self, command: ConnectedChatTurnClaimCommand) -> ConnectedChatTurnClaim:
        if type(command) is not ConnectedChatTurnClaimCommand:
            raise ConnectedChatTurnError("CONNECTED_CHAT_TURN_INVALID")
        try:
            value = await self._client.rpc(
                "connected_chat_claim_turn_v1",
                {
                    "p_owner_id": command.owner_id,
                    "p_chat_id": command.chat_id,
                    "p_message_id": command.message_id,
                    "p_origin_session_binding_sha256": (command.origin_session_binding_sha256),
                    "p_request_binding_sha256": command.request_binding_sha256,
                },
            )
        except Exception:
            raise ConnectedChatTurnError() from None
        if isinstance(value, list):
            if len(value) != 1:
                raise ConnectedChatTurnError("CONNECTED_CHAT_TURN_INVALID")
            value = value[0]
        if not isinstance(value, dict) or set(value) != _CLAIM_KEYS:
            raise ConnectedChatTurnError("CONNECTED_CHAT_TURN_INVALID")
        try:
            state = ConnectedChatTurnState(value["job_state"])
            stage = ConnectedChatTurnStage(value["stage"])
            turn_id = _uuid(value["turn_id"], "turn_id")  # type: ignore[arg-type]
            token_value = value["claim_token"]
            claim_token = (
                None if token_value is None else _uuid(token_value, "claim_token")  # type: ignore[arg-type]
            )
            response = value["response_data"]
            updated_at = _time(value["updated_at"], "updated_at")
            return ConnectedChatTurnClaim(
                state=state,
                turn_id=turn_id,
                stage=stage,
                claim_token=claim_token,
                response_data=response,  # type: ignore[arg-type]
                updated_at=updated_at,
            )
        except (TypeError, ValueError):
            raise ConnectedChatTurnError("CONNECTED_CHAT_TURN_INVALID") from None
