from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest

from backend.connected_app_contracts import ConnectorAccountKind
from backend.connected_app_policy import (
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_release_bootstrap import (
    CONNECTED_RELEASE_BOOTSTRAP_TARGETS,
    ConnectedReleaseBootstrapError,
    ConnectedReleaseBootstrapPermit,
    ConnectedReleaseDedicatedAccountPermit,
    bootstrap_request_id,
    parse_intercepted_callback,
)


def target(provider, account_kind, resource):
    return next(
        item
        for item in CONNECTED_RELEASE_BOOTSTRAP_TARGETS
        if item.provider is provider
        and item.account_kind is account_kind
        and item.resource is resource
    )


def test_exact_six_target_matrix_and_capability_truth() -> None:
    assert len(CONNECTED_RELEASE_BOOTSTRAP_TARGETS) == 6
    assert len({item.key for item in CONNECTED_RELEASE_BOOTSTRAP_TARGETS}) == 6
    mail = {
        ConnectorActionKind.MAIL_SEARCH,
        ConnectorActionKind.MAIL_GET,
        ConnectorActionKind.MAIL_CREATE_DRAFT,
        ConnectorActionKind.MAIL_SEND,
        ConnectorActionKind.MAIL_REPLY,
    }
    for item in CONNECTED_RELEASE_BOOTSTRAP_TARGETS:
        if item.resource is ConnectorResource.MAIL:
            assert item.actions == mail
        else:
            expected = {
                ConnectorActionKind.CALENDAR_LIST,
                ConnectorActionKind.CALENDAR_GET,
                ConnectorActionKind.CALENDAR_CREATE,
                ConnectorActionKind.CALENDAR_UPDATE,
                ConnectorActionKind.CALENDAR_CANCEL,
            }
            if not (
                item.provider is ConnectorProvider.MICROSOFT
                and item.account_kind is ConnectorAccountKind.PERSONAL
            ):
                expected.add(ConnectorActionKind.CALENDAR_FREE_BUSY)
            assert item.actions == expected


def test_google_scope_callback_is_accepted_but_code_state_whitespace_is_not() -> None:
    item = target(
        ConnectorProvider.GOOGLE,
        ConnectorAccountKind.PERSONAL,
        ConnectorResource.MAIL,
    )
    state = "s" * 43
    callback = parse_intercepted_callback(
        callback_url=(
            item.redirect_uri
            + "?code="
            + "c" * 43
            + "&state="
            + state
            + "&scope=openid%20email&authuser=0&prompt=consent"
        ),
        target=item,
        expected_state_sha256=hashlib.sha256(state.encode()).hexdigest(),
    )
    assert callback.provider is ConnectorProvider.GOOGLE
    with pytest.raises(ConnectedReleaseBootstrapError):
        parse_intercepted_callback(
            callback_url=item.redirect_uri + "?code=bad%20code&state=" + state,
            target=item,
            expected_state_sha256=hashlib.sha256(state.encode()).hexdigest(),
        )


def test_denial_must_bind_the_exact_current_state_before_it_is_actionable() -> None:
    item = target(
        ConnectorProvider.MICROSOFT,
        ConnectorAccountKind.WORK_SCHOOL,
        ConnectorResource.CALENDAR,
    )
    with pytest.raises(ConnectedReleaseBootstrapError) as caught:
        parse_intercepted_callback(
            callback_url=item.redirect_uri + "?error=access_denied&state=" + "x" * 43,
            target=item,
            expected_state_sha256=hashlib.sha256(("s" * 43).encode()).hexdigest(),
        )
    assert caught.value.code == "CONNECTED_RELEASE_BOOTSTRAP_CALLBACK_INVALID"


def test_bootstrap_and_dedicated_account_permits_are_nonreplayable() -> None:
    ceremony = str(uuid4())
    permit = ConnectedReleaseBootstrapPermit(
        ceremony_id=ceremony,
        confirmation=f"CONFIRM CONNECTED PREVIEW {ceremony}",
    )
    permit.consume(ceremony_id=ceremony)
    with pytest.raises(ConnectedReleaseBootstrapError):
        permit.consume(ceremony_id=ceremony)

    matrix = "a" * 64
    owner = str(uuid4())
    dedicated = ConnectedReleaseDedicatedAccountPermit(
        ceremony_id=ceremony,
        owner_id=owner,
        descriptor_matrix_sha256=matrix,
        confirmation=(
            "CONFIRM THREE DEDICATED NON-CUSTOMER ACCOUNTS "
            f"{ceremony} {matrix[:16]}"
        ),
    )
    attestation = dedicated.consume(
        ceremony_id=ceremony,
        owner_id=owner,
        descriptor_matrix_sha256=matrix,
    )
    assert attestation == hashlib.sha256(
        "\0".join(
            (
                "askcrump-release-preview-dedicated-account-attestation-v1",
                ceremony,
                owner,
                matrix,
                "three_dedicated_non_customer_accounts",
            )
        ).encode()
    ).hexdigest()
    with pytest.raises(ConnectedReleaseBootstrapError):
        dedicated.consume(
            ceremony_id=ceremony,
            owner_id=owner,
            descriptor_matrix_sha256=matrix,
        )


def test_attempt_generation_changes_durable_request_identity() -> None:
    ceremony = str(uuid4())
    item = CONNECTED_RELEASE_BOOTSTRAP_TARGETS[0]
    first = bootstrap_request_id(ceremony_id=ceremony, target=item, generation=1)
    second = bootstrap_request_id(ceremony_id=ceremony, target=item, generation=2)
    assert first != second
