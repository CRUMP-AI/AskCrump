from __future__ import annotations

import asyncio

import pytest

from backend.connected_app_ai_model import (
    ConnectedOperatorAIModel,
    ConnectedOperatorAIModelError,
)


OWNER = "00000000-0000-4000-8000-000000000001"
OWNER_B = "00000000-0000-4000-8000-000000000002"


class Gateway:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def gateway_text(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


@pytest.mark.asyncio
async def test_per_call_owner_bound_gateway_call_uses_fixed_purpose_and_bounds():
    gateway = Gateway('{"kind":"none"}')
    model = ConnectedOperatorAIModel(gateway)
    result = await model.complete(
        owner_id=OWNER,
        system="exact system",
        prompt="bounded prompt",
        max_tokens=2_000,
        timeout_seconds=20,
    )
    assert result == '{"kind":"none"}'
    assert gateway.calls == [
        {
            "system": "exact system",
            "prompt": "bounded prompt",
            "max_tokens": 2_000,
            "timeout_seconds": 20.0,
            "user_id": OWNER,
            "purpose": "connected_app_plan",
        }
    ]
    assert OWNER not in repr(model)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    (RuntimeError("provider detail"), "", "x" * (48 * 1024 + 1), object()),
    ids=("exception", "empty", "too-large", "wrong-type"),
)
async def test_model_dependency_failures_are_content_free(response):
    model = ConnectedOperatorAIModel(Gateway(response))
    with pytest.raises(ConnectedOperatorAIModelError) as error:
        await model.complete(
            owner_id=OWNER,
            system="system",
            prompt="prompt",
            max_tokens=128,
            timeout_seconds=5,
        )
    assert error.value.code == "CONNECTED_OPERATOR_MODEL_FAILED"
    assert "provider" not in str(error.value).lower()


@pytest.mark.asyncio
async def test_invalid_call_never_reaches_gateway():
    gateway = Gateway("must not run")
    model = ConnectedOperatorAIModel(gateway)
    with pytest.raises(ConnectedOperatorAIModelError):
        await model.complete(
            owner_id=OWNER,
            system="system",
            prompt="prompt",
            max_tokens=2_001,
            timeout_seconds=20,
        )
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_owner_binding_requires_canonical_uuid_before_gateway_call():
    gateway = Gateway("ok")
    model = ConnectedOperatorAIModel(gateway)
    with pytest.raises(ConnectedOperatorAIModelError):
        await model.complete(
            owner_id="00000000-0000-4000-8000-00000000000A",
            system="system",
            prompt="prompt",
            max_tokens=128,
            timeout_seconds=5,
        )
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_concurrent_owner_calls_remain_exactly_attributed():
    gateway = Gateway('{"kind":"none"}')
    model = ConnectedOperatorAIModel(gateway)
    await asyncio.gather(
        model.complete(
            owner_id=OWNER,
            system="system a",
            prompt="prompt a",
            max_tokens=128,
            timeout_seconds=5,
        ),
        model.complete(
            owner_id=OWNER_B,
            system="system b",
            prompt="prompt b",
            max_tokens=128,
            timeout_seconds=5,
        ),
    )
    assert {(call["user_id"], call["prompt"]) for call in gateway.calls} == {
        (OWNER, "prompt a"),
        (OWNER_B, "prompt b"),
    }
