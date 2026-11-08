"""Request-OIDC authenticated Vercel AI Gateway for connected planning.

The connected graph cannot use the build-time ``VERCEL_OIDC_TOKEN`` process
setting.  It receives the same nonserializable assertion that authenticated
the request-scoped KMS exchange and retains it only for the shorter graph-key
lifetime.  Requests are fixed-destination, no-proxy, no-redirect, bounded,
ZDR-only, provider-pinned, and cost-receipted before a response is accepted.
"""

from __future__ import annotations

import certifi
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import time
from typing import Protocol
from uuid import UUID, uuid4

import httpx

from .connected_app_kms import ConnectedVercelOIDCAssertion


_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,119}$")
_PROVIDER = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
_DEPLOYMENT = re.compile(r"^dpl_[A-Za-z0-9]{8,}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_PROMPT_BYTES = 64 * 1024
_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
_PURPOSES = {
    "connected_app_plan": ("planner", "feature:connected-app-plan"),
    "connected_app_delegated_response": (
        "chat",
        "feature:connected-app-delegated-response",
    ),
}


class ConnectedRequestAIGatewayError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("CONNECTED_REQUEST_AI_GATEWAY_FAILED")
        self.code = "CONNECTED_REQUEST_AI_GATEWAY_FAILED"


class ConnectedAIGatewayRPC(Protocol):
    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object: ...


def _truth(value: object) -> bool:
    if isinstance(value, list):
        return len(value) == 1 and value[0] is True
    return value is True


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedRequestAIGatewayError()
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise ConnectedRequestAIGatewayError() from None
    if canonical != value:
        raise ConnectedRequestAIGatewayError()
    return value


class ConnectedRequestScopedAIGateway:
    """One graph-generation gateway authenticated by one Vercel assertion."""

    __slots__ = (
        "__assertion",
        "_database",
        "_model",
        "_provider",
        "_deployment_id",
        "_commit_sha",
        "_transport",
    )

    def __init__(
        self,
        *,
        assertion: ConnectedVercelOIDCAssertion,
        database: ConnectedAIGatewayRPC,
        model: str,
        provider: str,
        deployment_id: str,
        commit_sha: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            type(assertion) is not ConnectedVercelOIDCAssertion
            or not callable(getattr(database, "rpc", None))
            or not isinstance(model, str)
            or not _MODEL.fullmatch(model)
            or not isinstance(provider, str)
            or not _PROVIDER.fullmatch(provider)
            or not isinstance(deployment_id, str)
            or not _DEPLOYMENT.fullmatch(deployment_id)
            or not isinstance(commit_sha, str)
            or not _COMMIT.fullmatch(commit_sha)
            or (transport is not None and not isinstance(transport, httpx.AsyncBaseTransport))
        ):
            raise ConnectedRequestAIGatewayError()
        self.__assertion = assertion
        self._database = database
        self._model = model
        self._provider = provider
        self._deployment_id = deployment_id
        self._commit_sha = commit_sha
        self._transport = transport

    async def _claim(self, receipt_id: str, *, purpose: str) -> None:
        try:
            receipt_lane, _feature_tag = _PURPOSES[purpose]
        except (KeyError, TypeError):
            raise ConnectedRequestAIGatewayError() from None
        try:
            result = await self._database.rpc(
                "claim_ai_gateway_cost_receipt",
                {
                    "p_receipt_id": receipt_id,
                    "p_environment": "production",
                    "p_deployment_id": self._deployment_id,
                    "p_commit_sha": self._commit_sha,
                    # Map each exact public connected purpose to an existing,
                    # bounded cost-receipt lane. Unknown purposes fail before
                    # a claim or any network I/O.
                    "p_purpose": receipt_lane,
                    "p_expected_model": self._model,
                    "p_expected_provider": self._provider,
                    "p_authentication_lane": "oidc-project",
                },
                retry_transient=False,
            )
        except Exception:
            raise ConnectedRequestAIGatewayError() from None
        if not _truth(result):
            raise ConnectedRequestAIGatewayError()

    @staticmethod
    def _usage(data: dict[str, object]) -> tuple[int, int, int, bool]:
        usage = data.get("usage")
        values = usage if isinstance(usage, dict) else {}

        def integer(*names: str) -> int | None:
            for name in names:
                raw = values.get(name)
                if isinstance(raw, bool):
                    continue
                try:
                    result = int(raw)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if result >= 0:
                    return result
            return None

        input_tokens = integer("prompt_tokens", "input_tokens")
        output_tokens = integer("completion_tokens", "output_tokens")
        details = values.get("prompt_tokens_details") or values.get(
            "input_tokens_details"
        )
        detail_values = details if isinstance(details, dict) else {}
        try:
            cached = max(
                0,
                int(
                    detail_values.get(
                        "cached_tokens",
                        detail_values.get("cached_input_tokens", 0),
                    )
                    or 0
                ),
            )
        except (TypeError, ValueError):
            cached = 0
        return (
            input_tokens or 0,
            output_tokens or 0,
            cached,
            input_tokens is not None and output_tokens is not None,
        )

    @staticmethod
    def _cost(data: dict[str, object]) -> tuple[str | None, bool]:
        metadata = data.get("providerMetadata") or data.get("provider_metadata")
        metadata_values = metadata if isinstance(metadata, dict) else {}
        gateway = metadata_values.get("gateway")
        gateway_values = gateway if isinstance(gateway, dict) else {}
        try:
            value = Decimal(str(gateway_values.get("cost")))
        except (InvalidOperation, TypeError, ValueError):
            return None, False
        if not value.is_finite() or value < 0:
            return None, False
        return format(value, "f"), True

    def _privacy_routing_attested(self, data: dict[str, object]) -> bool:
        """Require the gateway's per-response routing audit before using output.

        Request options are the enforcement mechanism. The response audit is
        independent proof that the call crossed the pinned provider-selection
        boundary. A successful model response without this metadata is not
        sufficient for connected customer data.
        """

        metadata = data.get("providerMetadata") or data.get("provider_metadata")
        metadata_values = metadata if isinstance(metadata, dict) else {}
        gateway = metadata_values.get("gateway")
        gateway_values = gateway if isinstance(gateway, dict) else {}
        routing = gateway_values.get("routing")
        routing_values = routing if isinstance(routing, dict) else {}
        final_provider = routing_values.get("finalProvider")
        if final_provider is None:
            final_provider = routing_values.get("final_provider")
        planning = routing_values.get("planningReasoning")
        if planning is None:
            planning = routing_values.get("planning_reasoning")
        return (
            final_provider == self._provider
            and isinstance(planning, str)
            and 0 < len(planning.strip()) <= 8_192
        )

    async def _settle(
        self,
        *,
        receipt_id: str,
        status: str,
        error_code: str | None,
        latency_ms: int,
        data: dict[str, object] | None = None,
    ) -> None:
        values = data if isinstance(data, dict) else {}
        input_tokens, output_tokens, cached, usage_complete = self._usage(values)
        cost, cost_complete = self._cost(values)
        try:
            result = await self._database.rpc(
                "settle_ai_gateway_cost_receipt",
                {
                    "p_receipt_id": receipt_id,
                    "p_status": status,
                    "p_error_code": error_code,
                    "p_model": str(values.get("model") or self._model)[:120],
                    "p_provider": self._provider,
                    "p_input_tokens": input_tokens,
                    "p_output_tokens": output_tokens,
                    "p_cached_input_tokens": cached,
                    "p_gross_cost_usd": cost,
                    "p_latency_ms": max(0, min(600_000, latency_ms)),
                    "p_usage_receipt_complete": usage_complete,
                    "p_cost_receipt_complete": cost_complete,
                },
                retry_transient=False,
            )
        except Exception:
            raise ConnectedRequestAIGatewayError() from None
        if not _truth(result):
            raise ConnectedRequestAIGatewayError()

    @staticmethod
    async def _read_json(response: httpx.Response) -> dict[str, object]:
        if response.is_redirect or response.status_code != 200:
            raise ConnectedRequestAIGatewayError()
        if response.headers.get("content-type", "").split(";", 1)[0].casefold() != (
            "application/json"
        ):
            raise ConnectedRequestAIGatewayError()
        declared = response.headers.get("content-length")
        if declared is not None:
            try:
                if not 0 < int(declared) <= _MAX_RESPONSE_BYTES:
                    raise ValueError
            except ValueError:
                raise ConnectedRequestAIGatewayError() from None
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                raise ConnectedRequestAIGatewayError()
            body.extend(chunk)
        if not body:
            raise ConnectedRequestAIGatewayError()
        try:
            value = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
            raise ConnectedRequestAIGatewayError() from None
        if not isinstance(value, dict):
            raise ConnectedRequestAIGatewayError()
        return value

    async def gateway_text(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: float,
        user_id: str | None,
        purpose: str,
    ) -> str:
        if (
            not isinstance(system, str)
            or not system
            or not isinstance(prompt, str)
            or not prompt
            or len(system.encode("utf-8")) + len(prompt.encode("utf-8"))
            > _MAX_PROMPT_BYTES
            or type(max_tokens) is not int
            or not 128 <= max_tokens <= 2_000
            or not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 5 <= float(timeout_seconds) <= 20
            or purpose not in _PURPOSES
        ):
            raise ConnectedRequestAIGatewayError()
        owner_id = _uuid(user_id)
        owner_pseudonym = hashlib.sha256(
            b"askcrump.connected-ai-owner/v1\0" + owner_id.encode("ascii")
        ).hexdigest()
        receipt_id = str(uuid4())
        await self._claim(receipt_id, purpose=purpose)
        _receipt_lane, feature_tag = _PURPOSES[purpose]
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "stream": False,
            # The gateway may use ``user`` for abuse isolation, but it does
            # not need Ask Crump's database owner UUID.  Send a stable,
            # domain-separated pseudonym instead of an account identifier.
            "user": owner_pseudonym,
            "tags": [feature_tag, "tier:connected"],
            "providerOptions": {
                "gateway": {
                    "only": [self._provider],
                    "disallowPromptTraining": True,
                    "zeroDataRetention": True,
                }
            },
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                http2=True,
                verify=certifi.where(),
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(
                    float(timeout_seconds),
                    connect=min(5.0, float(timeout_seconds)),
                    write=min(10.0, float(timeout_seconds)),
                    pool=5.0,
                ),
                transport=self._transport,
            ) as client:
                async with client.stream(
                    "POST",
                    _URL,
                    headers={
                        "Authorization": (
                            "Bearer " + self.__assertion.reveal_for_exchange()
                        ),
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json=body,
                ) as response:
                    data = await self._read_json(response)
        except ConnectedRequestAIGatewayError:
            await self._settle(
                receipt_id=receipt_id,
                status="failed",
                error_code="CONNECTED_REQUEST_AI_GATEWAY_FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
            raise
        except (httpx.HTTPError, ValueError, TypeError):
            await self._settle(
                receipt_id=receipt_id,
                status="failed",
                error_code="CONNECTED_REQUEST_AI_GATEWAY_FAILED",
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
            raise ConnectedRequestAIGatewayError() from None
        choices = data.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        _input_tokens, _output_tokens, _cached, usage_complete = self._usage(data)
        _cost, cost_complete = self._cost(data)
        if (
            data.get("model") != self._model
            or not isinstance(content, str)
            or not content.strip()
            or not usage_complete
            or not cost_complete
            or not self._privacy_routing_attested(data)
        ):
            await self._settle(
                receipt_id=receipt_id,
                status="failed",
                error_code="CONNECTED_REQUEST_AI_GATEWAY_INVALID_RESPONSE",
                latency_ms=round((time.perf_counter() - started) * 1000),
                data=data,
            )
            raise ConnectedRequestAIGatewayError()
        await self._settle(
            receipt_id=receipt_id,
            status="completed",
            error_code=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            data=data,
        )
        return content.strip()

    def __repr__(self) -> str:
        return "ConnectedRequestScopedAIGateway(authentication='request-oidc')"

    def __getstate__(self) -> object:
        raise TypeError("connected request AI gateways cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected request AI gateways cannot be serialized")


class ConnectedRequestScopedAIGatewayFactory:
    __slots__ = ("_database", "_model", "_provider", "_deployment_id", "_commit_sha")

    def __init__(
        self,
        *,
        database: ConnectedAIGatewayRPC,
        model: str,
        provider: str,
        deployment_id: str,
        commit_sha: str,
    ) -> None:
        # Validate once with a syntactically valid opaque assertion, without
        # retaining it or performing any I/O.
        if (
            not callable(getattr(database, "rpc", None))
            or not _MODEL.fullmatch(str(model or ""))
            or not _PROVIDER.fullmatch(str(provider or ""))
            or not _DEPLOYMENT.fullmatch(str(deployment_id or ""))
            or not _COMMIT.fullmatch(str(commit_sha or ""))
        ):
            raise ConnectedRequestAIGatewayError()
        self._database = database
        self._model = model
        self._provider = provider
        self._deployment_id = deployment_id
        self._commit_sha = commit_sha

    def build(
        self,
        *,
        assertion: ConnectedVercelOIDCAssertion,
    ) -> ConnectedRequestScopedAIGateway:
        return ConnectedRequestScopedAIGateway(
            assertion=assertion,
            database=self._database,
            model=self._model,
            provider=self._provider,
            deployment_id=self._deployment_id,
            commit_sha=self._commit_sha,
        )

    def __repr__(self) -> str:
        return "ConnectedRequestScopedAIGatewayFactory(authentication='request-oidc')"

    def __getstate__(self) -> object:
        raise TypeError("connected request AI gateway factories cannot be serialized")

    def __reduce__(self) -> object:
        raise TypeError("connected request AI gateway factories cannot be serialized")


__all__ = [
    "ConnectedRequestAIGatewayError",
    "ConnectedRequestScopedAIGateway",
    "ConnectedRequestScopedAIGatewayFactory",
]
