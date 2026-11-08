import pytest

from backend.connected_app_payload_retention import (
    ConnectedPayloadRetentionError,
    SupabaseConnectedPayloadRetentionPurger,
)


class RPC:
    def __init__(self, response=None, *, failure=False):
        self.response = (
            {
                "payloads_purged": 2,
                "plans_purged": 3,
                "loop_envelopes_purged": 4,
            }
            if response is None
            else response
        )
        self.failure = failure
        self.calls = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, payload, retry_transient))
        if self.failure:
            raise RuntimeError("database detail must be quarantined")
        return self.response


@pytest.mark.asyncio
async def test_bounded_purge_uses_one_content_free_atomic_rpc():
    rpc = RPC()
    subject = SupabaseConnectedPayloadRetentionPurger(rpc)
    result = await subject.run_bounded(
        payload_maximum=7, plan_maximum=9, loop_maximum=11
    )
    assert result.payloads_purged == 2
    assert result.plans_purged == 3
    assert result.loop_envelopes_purged == 4
    assert rpc.calls == [
        (
            "connected_app_purge_expired_ciphertext_v1",
            {
                "p_payload_maximum": 7,
                "p_plan_maximum": 9,
                "p_loop_maximum": 11,
            },
            False,
        )
    ]
    assert "database detail" not in repr(subject)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    (
        {},
        {"payloads_purged": 1},
        {"payloads_purged": True, "plans_purged": 0, "loop_envelopes_purged": 0},
        {"payloads_purged": 8, "plans_purged": 0, "loop_envelopes_purged": 0},
        {"payloads_purged": 0, "plans_purged": -1, "loop_envelopes_purged": 0},
        {"payloads_purged": 0, "plans_purged": 0, "loop_envelopes_purged": 12},
    ),
)
async def test_malformed_or_out_of_bound_response_fails_closed(response):
    with pytest.raises(ConnectedPayloadRetentionError) as caught:
        await SupabaseConnectedPayloadRetentionPurger(RPC(response)).run_bounded(
            payload_maximum=7, plan_maximum=9, loop_maximum=11
        )
    assert caught.value.code == "CONNECTED_PAYLOAD_RETENTION_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_store_failure_is_redacted_and_retryable():
    with pytest.raises(ConnectedPayloadRetentionError) as caught:
        await SupabaseConnectedPayloadRetentionPurger(RPC(failure=True)).run_bounded()
    assert caught.value.code == "CONNECTED_PAYLOAD_RETENTION_UNAVAILABLE"
    assert caught.value.retryable is True
    assert "database detail" not in repr(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload_maximum,plan_maximum,loop_maximum",
    ((0, 1, 1), (1, 0, 1), (101, 1, 1), (1, True, 1), (1, 1, 0)),
)
async def test_limits_are_exact_positive_integers(
    payload_maximum, plan_maximum, loop_maximum
):
    with pytest.raises(ConnectedPayloadRetentionError) as caught:
        await SupabaseConnectedPayloadRetentionPurger(RPC()).run_bounded(
            payload_maximum=payload_maximum,
            plan_maximum=plan_maximum,
            loop_maximum=loop_maximum,
        )
    assert caught.value.code == "CONNECTED_PAYLOAD_RETENTION_INVALID"
