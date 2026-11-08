"""Typed production keys for the connected-operator dependency graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from .connected_app_chat_completion import ConnectedChatCompletionKey
from .connected_app_chat_turn import ConnectedChatBindingKey
from .connected_app_credential_vault import ConnectedCredentialMasterKey
from .connected_app_durable_oauth import ConnectedOAuthMasterKey
from .connected_app_key_derivation import (
    ConnectedDerivedKeyset,
    ConnectedKeyDerivationError,
    ConnectedKeyPurpose,
)
from .connected_app_host_configuration import ConnectedHostConfigurationKey
from .connected_app_multi_step import (
    ConnectedMultiStepCommitmentKey,
    ConnectedMultiStepMasterKey,
)
from .connected_app_payload_vault import (
    ConnectedPayloadCommitmentKey,
    ConnectedPayloadMasterKey,
)
from .connected_app_plan_once import ConnectedPlanBindingKey
from .connected_app_plan_vault import (
    ConnectedPlanCommitmentKey,
    ConnectedPlanMasterKey,
)
from .connected_app_readiness_attestation import ConnectedReadinessAttestationKey
from .connected_app_schedule_adapters import (
    ConnectedScheduleTemplateCommitmentKey,
    ConnectedScheduleTemplateKey,
)


@dataclass(frozen=True, slots=True, repr=False)
class ConnectedProductionKeys:
    """All typed graph keys, each created from a distinct HKDF domain."""

    host_configuration: ConnectedHostConfigurationKey
    readiness_attestation: ConnectedReadinessAttestationKey
    oauth_envelope: ConnectedOAuthMasterKey
    oauth_permit: ConnectedOAuthMasterKey
    oauth_code_envelope: ConnectedOAuthMasterKey
    credential_envelope: ConnectedCredentialMasterKey
    payload_envelope: ConnectedPayloadMasterKey
    payload_commitment: ConnectedPayloadCommitmentKey
    plan_envelope: ConnectedPlanMasterKey
    plan_commitment: ConnectedPlanCommitmentKey
    plan_binding: ConnectedPlanBindingKey
    schedule_envelope: ConnectedScheduleTemplateKey
    schedule_commitment: ConnectedScheduleTemplateCommitmentKey
    chat_binding: ConnectedChatBindingKey
    chat_completion: ConnectedChatCompletionKey
    loop_envelope: ConnectedMultiStepMasterKey
    loop_commitment: ConnectedMultiStepCommitmentKey
    composition_manifest_sha256: str
    root_key_id: str
    custody_attestation_sha256: str
    expires_at: datetime

    @classmethod
    def build(
        cls,
        keyset: ConnectedDerivedKeyset,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> ConnectedProductionKeys:
        if type(keyset) is not ConnectedDerivedKeyset or not callable(now):
            raise ConnectedKeyDerivationError("CONNECTED_KEY_CUSTODY_INVALID")
        keyset.require_current(now=now())

        def identifier(purpose: ConnectedKeyPurpose) -> str:
            return keyset.key_id(purpose)

        def secret(purpose: ConnectedKeyPurpose) -> bytes:
            return keyset.key(purpose)

        return cls(
            host_configuration=ConnectedHostConfigurationKey(
                identifier(ConnectedKeyPurpose.HOST_CONFIGURATION),
                secret(ConnectedKeyPurpose.HOST_CONFIGURATION),
            ),
            readiness_attestation=ConnectedReadinessAttestationKey(
                identifier(ConnectedKeyPurpose.READINESS_ATTESTATION),
                secret(ConnectedKeyPurpose.READINESS_ATTESTATION),
            ),
            oauth_envelope=ConnectedOAuthMasterKey(
                identifier(ConnectedKeyPurpose.OAUTH_ENVELOPE),
                secret(ConnectedKeyPurpose.OAUTH_ENVELOPE),
            ),
            oauth_permit=ConnectedOAuthMasterKey(
                identifier(ConnectedKeyPurpose.OAUTH_PERMIT),
                secret(ConnectedKeyPurpose.OAUTH_PERMIT),
            ),
            oauth_code_envelope=ConnectedOAuthMasterKey(
                identifier(ConnectedKeyPurpose.OAUTH_CODE_ENVELOPE),
                secret(ConnectedKeyPurpose.OAUTH_CODE_ENVELOPE),
            ),
            credential_envelope=ConnectedCredentialMasterKey(
                identifier(ConnectedKeyPurpose.CREDENTIAL_ENVELOPE),
                secret(ConnectedKeyPurpose.CREDENTIAL_ENVELOPE),
            ),
            payload_envelope=ConnectedPayloadMasterKey(
                identifier(ConnectedKeyPurpose.PAYLOAD_ENVELOPE),
                secret(ConnectedKeyPurpose.PAYLOAD_ENVELOPE),
            ),
            payload_commitment=ConnectedPayloadCommitmentKey(
                identifier(ConnectedKeyPurpose.PAYLOAD_COMMITMENT),
                secret(ConnectedKeyPurpose.PAYLOAD_COMMITMENT),
            ),
            plan_envelope=ConnectedPlanMasterKey(
                identifier(ConnectedKeyPurpose.PLAN_ENVELOPE),
                secret(ConnectedKeyPurpose.PLAN_ENVELOPE),
            ),
            plan_commitment=ConnectedPlanCommitmentKey(
                identifier(ConnectedKeyPurpose.PLAN_COMMITMENT),
                secret(ConnectedKeyPurpose.PLAN_COMMITMENT),
            ),
            plan_binding=ConnectedPlanBindingKey(
                identifier(ConnectedKeyPurpose.PLAN_BINDING),
                secret(ConnectedKeyPurpose.PLAN_BINDING),
            ),
            schedule_envelope=ConnectedScheduleTemplateKey(
                identifier(ConnectedKeyPurpose.SCHEDULE_ENVELOPE),
                secret(ConnectedKeyPurpose.SCHEDULE_ENVELOPE),
            ),
            schedule_commitment=ConnectedScheduleTemplateCommitmentKey(
                identifier(ConnectedKeyPurpose.SCHEDULE_COMMITMENT),
                secret(ConnectedKeyPurpose.SCHEDULE_COMMITMENT),
            ),
            chat_binding=ConnectedChatBindingKey(
                identifier(ConnectedKeyPurpose.CHAT_BINDING),
                secret(ConnectedKeyPurpose.CHAT_BINDING),
            ),
            chat_completion=ConnectedChatCompletionKey(
                identifier(ConnectedKeyPurpose.CHAT_COMPLETION),
                secret(ConnectedKeyPurpose.CHAT_COMPLETION),
            ),
            loop_envelope=ConnectedMultiStepMasterKey(
                identifier(ConnectedKeyPurpose.LOOP_ENVELOPE),
                secret(ConnectedKeyPurpose.LOOP_ENVELOPE),
            ),
            loop_commitment=ConnectedMultiStepCommitmentKey(
                identifier(ConnectedKeyPurpose.LOOP_COMMITMENT),
                secret(ConnectedKeyPurpose.LOOP_COMMITMENT),
            ),
            composition_manifest_sha256=keyset.composition_manifest_sha256,
            root_key_id=keyset.root_key_id,
            custody_attestation_sha256=keyset.attestation_sha256,
            expires_at=keyset.expires_at,
        )

    def __repr__(self) -> str:
        return "ConnectedProductionKeys(custody='attested', keys='<redacted>')"

    def __getstate__(self) -> object:
        raise TypeError("connected production keys cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected production keys cannot be serialized")


__all__ = ["ConnectedProductionKeys"]
