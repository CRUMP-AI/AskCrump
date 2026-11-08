from __future__ import annotations

import hashlib

import pytest

from backend.connected_app_contracts import ConnectorAccountKind
from backend.connected_app_policy import ConnectorProvider, ConnectorResource
from backend.connected_app_release_effect_ledger import (
    ConnectedReleasePreviewAuthorityPhase,
    ConnectedReleasePreviewEffectError,
    ConnectedReleasePreviewEffectLedger,
    ConnectedReleasePreviewEffectPhase,
    release_preview_marker,
)


INVOCATION = "11111111-1111-4111-8111-111111111111"
SHA = hashlib.sha256(b"contract").hexdigest()


class Database:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.authority_rows: list[dict[str, object]] = []
        self.calls: list[tuple[str, dict[str, object], bool]] = []
        self.lose_begin = False
        self.lose_transition = False
        self.lose_fail = False
        self.failed = False

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        if name == "connected_app_release_preview_begin_v1":
            if not self.rows:
                self.rows = [
                    {
                        **item,
                        "invocation_id": payload["p_invocation_id"],
                        "phase": "pending",
                        "revision": 0,
                        "artifact_id_sha256": None,
                    }
                    for item in payload["p_effects"]
                ]
                self.authority_rows = [
                    {
                        "invocation_id": payload["p_invocation_id"],
                        "provider": provider,
                        "account_kind": account_kind,
                        "phase": "pending",
                        "revision": 0,
                        "provider_receipt_sha256": None,
                    }
                    for provider, account_kind in (
                        ("google", payload["p_google_account_kind"]),
                        ("microsoft", "personal"),
                        ("microsoft", "work_school"),
                    )
                ]
            if self.lose_begin:
                raise TimeoutError
            return {"created": True}
        if name == "connected_app_release_preview_status_v1":
            return [dict(row) for row in self.rows]
        if name == "connected_app_release_preview_authority_status_v1":
            return [dict(row) for row in self.authority_rows]
        if name == "connected_app_release_preview_authority_v1":
            row = next(
                item
                for item in self.authority_rows
                if item["provider"] == payload["p_provider"]
                and item["account_kind"] == payload["p_account_kind"]
            )
            assert row["phase"] == payload["p_expected_phase"]
            assert row["revision"] == payload["p_expected_revision"]
            row["phase"] = payload["p_next_phase"]
            row["revision"] = int(row["revision"]) + 1
            row["provider_receipt_sha256"] = payload[
                "p_provider_receipt_sha256"
            ]
            return dict(row)
        if name == "connected_app_release_preview_effect_v1":
            row = next(
                item
                for item in self.rows
                if item["effect_id"] == payload["p_effect_id"]
            )
            assert row["phase"] == payload["p_expected_phase"]
            assert row["revision"] == payload["p_expected_revision"]
            row["phase"] = payload["p_next_phase"]
            row["revision"] = int(row["revision"]) + 1
            row["artifact_id_sha256"] = (
                payload["p_artifact_id_sha256"]
                if payload["p_artifact_id_sha256"] is not None
                else row["artifact_id_sha256"]
            )
            if self.lose_transition:
                raise TimeoutError
            return {"updated": True}
        if name == "connected_app_release_preview_finalize_v1":
            unsettled = sum(
                row["phase"]
                != (
                    "retained_test_artifact"
                    if row["resource"] == "mail"
                    else "clean"
                )
                for row in self.rows
            )
            unsettled += sum(
                row["phase"] != "local_retired" for row in self.authority_rows
            )
            return {
                "invocation_id": payload["p_invocation_id"],
                "status": "clean" if unsettled == 0 else "unsettled",
                "unsettled_effects": unsettled,
            }
        if name == "connected_app_release_preview_fail_v1":
            if not self.failed:
                assert all(
                    row["phase"] == "local_retired"
                    for row in self.authority_rows
                )
                assert not any(
                    row["phase"] in {"observed", "cleanup"}
                    for row in self.rows
                )
                for row in self.rows:
                    if row["phase"] in {"pending", "dispatched"}:
                        row["phase"] = "effect_unknown"
                        row["revision"] = int(row["revision"]) + 1
                self.failed = True
            value = {
                "invocation_id": payload["p_invocation_id"],
                "status": "failed",
                "unknown_effects": sum(
                    row["phase"] == "effect_unknown" for row in self.rows
                ),
            }
            if self.lose_fail:
                self.lose_fail = False
                raise TimeoutError
            return value
        raise AssertionError(name)


def deployment() -> dict[str, str]:
    return {
        "composition_manifest_sha256": SHA,
        "database_contract_sha256": SHA,
        "database_target_fingerprint": "1" * 32,
        "provider_contract_sha256": SHA,
        "deployment_id": "dpl_12345678abcd",
        "commit_sha": "a" * 40,
        "host_configuration_ciphertext_sha256": SHA,
        "root_key_id": "gkms1",
    }


@pytest.mark.asyncio
async def test_manifest_is_exact_content_free_and_response_loss_recovers() -> None:
    database = Database()
    database.lose_begin = True
    ledger = ConnectedReleasePreviewEffectLedger(
        database=database,
        invocation_id=INVOCATION,
    )
    manifest = await ledger.begin(
        google_account_kind=ConnectorAccountKind.PERSONAL,
        descriptor_matrix_sha256=SHA,
        dedicated_account_attestation_sha256=SHA,
        deployment=deployment(),
        release_preview_contract_sha256=SHA,
    )
    assert len(manifest) == 64
    assert ledger.effect_manifest_sha256 == manifest
    assert len(await ledger.states()) == 6
    raw_marker = release_preview_marker(
        invocation_id=INVOCATION,
        provider=ConnectorProvider.GOOGLE,
        account_kind=ConnectorAccountKind.PERSONAL,
        resource=ConnectorResource.MAIL,
    )
    assert all(raw_marker not in repr(row) for row in database.rows)
    assert {
        (row["provider"], row["account_kind"], row["resource"])
        for row in database.rows
    } == {
        ("google", "personal", "mail"),
        ("google", "personal", "calendar"),
        ("microsoft", "personal", "mail"),
        ("microsoft", "personal", "calendar"),
        ("microsoft", "work_school", "mail"),
        ("microsoft", "work_school", "calendar"),
    }


@pytest.mark.asyncio
async def test_transition_response_loss_requires_exact_readback_and_final_zero() -> None:
    database = Database()
    ledger = ConnectedReleasePreviewEffectLedger(
        database=database,
        invocation_id=INVOCATION,
    )
    await ledger.begin(
        google_account_kind=ConnectorAccountKind.PERSONAL,
        descriptor_matrix_sha256=SHA,
        dedicated_account_attestation_sha256=SHA,
        deployment=deployment(),
        release_preview_contract_sha256=SHA,
    )
    state = await ledger.state_for(
        provider=ConnectorProvider.GOOGLE,
        account_kind=ConnectorAccountKind.PERSONAL,
        resource=ConnectorResource.MAIL,
    )
    database.lose_transition = True
    state = await ledger.transition(
        state=state,
        next_phase=ConnectedReleasePreviewEffectPhase.DISPATCHED,
    )
    assert state.revision == 1
    assert state.phase is ConnectedReleasePreviewEffectPhase.DISPATCHED
    with pytest.raises(ConnectedReleasePreviewEffectError):
        await ledger.finalize()
    database.lose_transition = False
    for effect in tuple((await ledger.states()).values()):
        terminal = (
            ConnectedReleasePreviewEffectPhase.RETAINED_TEST_ARTIFACT
            if effect.resource is ConnectorResource.MAIL
            else ConnectedReleasePreviewEffectPhase.CLEAN
        )
        while effect.phase is not terminal:
            next_phase = {
                ConnectedReleasePreviewEffectPhase.PENDING: (
                    ConnectedReleasePreviewEffectPhase.DISPATCHED
                ),
                ConnectedReleasePreviewEffectPhase.DISPATCHED: (
                    ConnectedReleasePreviewEffectPhase.OBSERVED
                ),
                ConnectedReleasePreviewEffectPhase.OBSERVED: (
                    ConnectedReleasePreviewEffectPhase.CLEANUP
                ),
                ConnectedReleasePreviewEffectPhase.CLEANUP: (
                    terminal
                ),
            }[effect.phase]
            effect = await ledger.transition(
                state=effect,
                next_phase=next_phase,
                artifact_id=(
                    "retained-artifact-id"
                    if next_phase
                    is ConnectedReleasePreviewEffectPhase.OBSERVED
                    else None
                ),
            )
    for authority in tuple((await ledger.authorities()).values()):
        if authority.provider is ConnectorProvider.GOOGLE:
            authority = await ledger.transition_authority(
                state=authority,
                next_phase=(
                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                ),
            )
            authority = await ledger.transition_authority(
                state=authority,
                next_phase=(
                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED
                ),
                provider_receipt_sha256=SHA,
            )
        await ledger.transition_authority(
            state=authority,
            next_phase=ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED,
        )
    await ledger.finalize()


@pytest.mark.asyncio
async def test_failed_terminal_recovers_lost_response_without_fabricating_clean() -> None:
    database = Database()
    ledger = ConnectedReleasePreviewEffectLedger(
        database=database,
        invocation_id=INVOCATION,
    )
    await ledger.begin(
        google_account_kind=ConnectorAccountKind.PERSONAL,
        descriptor_matrix_sha256=SHA,
        dedicated_account_attestation_sha256=SHA,
        deployment=deployment(),
        release_preview_contract_sha256=SHA,
    )
    for effect in tuple((await ledger.states()).values()):
        await ledger.transition(
            state=effect,
            next_phase=ConnectedReleasePreviewEffectPhase.DISPATCHED,
        )
    for authority in tuple((await ledger.authorities()).values()):
        if authority.provider is ConnectorProvider.GOOGLE:
            authority = await ledger.transition_authority(
                state=authority,
                next_phase=(
                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_DISPATCHED
                ),
            )
            authority = await ledger.transition_authority(
                state=authority,
                next_phase=(
                    ConnectedReleasePreviewAuthorityPhase.REVOCATION_ATTESTED
                ),
                provider_receipt_sha256=SHA,
            )
        await ledger.transition_authority(
            state=authority,
            next_phase=ConnectedReleasePreviewAuthorityPhase.LOCAL_RETIRED,
        )
    database.lose_fail = True
    await ledger.fail()
    assert database.failed is True
    assert all(
        row["phase"] == ConnectedReleasePreviewEffectPhase.EFFECT_UNKNOWN.value
        for row in database.rows
    )
    assert sum(
        call[0] == "connected_app_release_preview_fail_v1"
        for call in database.calls
    ) == 2


def test_marker_is_deterministic_bounded_and_account_kind_separated() -> None:
    personal = release_preview_marker(
        invocation_id=INVOCATION,
        provider=ConnectorProvider.MICROSOFT,
        account_kind=ConnectorAccountKind.PERSONAL,
        resource=ConnectorResource.MAIL,
    )
    work = release_preview_marker(
        invocation_id=INVOCATION,
        provider=ConnectorProvider.MICROSOFT,
        account_kind=ConnectorAccountKind.WORK_SCHOOL,
        resource=ConnectorResource.MAIL,
    )
    assert personal != work
    assert len(personal) < 200
    assert "@" not in personal
