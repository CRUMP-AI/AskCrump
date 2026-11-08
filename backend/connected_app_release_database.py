"""Sealed PostgREST authority for the one-shot connected release ceremony."""

from __future__ import annotations

import json
import os
import re

import certifi
import httpx

from . import config


_FUNCTION = re.compile(r"^[a-z][a-z0-9_]{2,95}$")
_MAX_RESPONSE_BYTES = 1_048_576
_ALLOWED_FUNCTIONS = frozenset(
    {
        "claim_ai_gateway_cost_receipt",
        "settle_ai_gateway_cost_receipt",
        "connected_app_get_binding_v2",
        "connected_app_oauth_read_completion_v3",
        "connected_app_credential_read_v1",
        "connected_app_credential_replace_v1",
        "connected_app_credential_delete_v1",
        "connected_app_credential_claim_refresh_v2",
        "connected_app_credential_finish_refresh_v2",
        "connected_app_credential_commit_refresh_v2",
        "connected_app_credential_quarantine_refresh_v2",
        "connected_app_operator_accept_oauth_callback_v2",
        "connected_app_oauth_code_read_v1",
        "connected_app_oauth_code_claim_v1",
        "connected_app_oauth_code_retire_v1",
        "connected_app_release_bootstrap_authenticate_v1",
        "connected_app_release_bootstrap_attest_dedicated_v1",
        "connected_app_release_bootstrap_read_dedicated_v1",
        "connected_app_release_preview_retire_connection_v1",
        "connected_app_release_preview_begin_v1",
        "connected_app_release_preview_authority_status_v1",
        "connected_app_release_preview_authority_v1",
        "connected_app_release_preview_effect_v1",
        "connected_app_release_preview_fail_v1",
        "connected_app_release_preview_finalize_v1",
        "connected_app_release_preview_status_v1",
        "connected_app_claim_release_preview_ceremony_v1",
        "connected_app_read_release_preview_ceremony_v1",
        "connected_app_issue_provider_smoke_challenge_v1",
        "connected_app_record_provider_smoke_v1",
        "connected_app_runtime_readiness_v1",
    }
)


class ConnectedReleasePreviewDatabaseError(RuntimeError):
    def __init__(self) -> None:
        self.code = "CONNECTED_RELEASE_PREVIEW_DATABASE_FAILED"
        super().__init__(self.code)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


class ConnectedReleasePreviewProductionDatabase:
    """Use only runtime Supabase custody with fixed-host, no-proxy HTTPS."""

    __slots__ = ()

    @staticmethod
    def _production_authority() -> tuple[str, str]:
        """Read only the two release-DB settings after the source lock."""

        environment = os.getenv("APP_ENV", os.getenv("VERCEL_ENV", "")).lower()
        origin = os.getenv("SUPABASE_URL", "").rstrip("/")
        service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if (
            environment != "production"
            or origin != config.PRODUCTION_SUPABASE_ORIGIN
            or not isinstance(service_key, str)
            or not 32 <= len(service_key) <= 16_384
            or any(ord(character) <= 32 or ord(character) == 127 for character in service_key)
        ):
            raise ConnectedReleasePreviewDatabaseError()
        return origin, service_key

    @classmethod
    def production_eligible(cls) -> bool:
        try:
            cls._production_authority()
            return True
        except Exception:
            return False

    async def rpc(
        self,
        function_name: str,
        payload: dict[str, object],
        *,
        retry_transient: bool = False,
    ) -> object:
        del retry_transient  # Every ceremony RPC is deliberately single-attempt.
        if (
            type(self) is not ConnectedReleasePreviewProductionDatabase
            or not isinstance(function_name, str)
            or _FUNCTION.fullmatch(function_name) is None
            or function_name not in _ALLOWED_FUNCTIONS
            or type(payload) is not dict
            or not self.production_eligible()
        ):
            raise ConnectedReleasePreviewDatabaseError()
        origin, service_key = self._production_authority()
        url = f"{origin}/rest/v1/rpc/{function_name}"
        timeout = httpx.Timeout(20.0, connect=5.0, write=10.0, read=20.0, pool=5.0)
        try:
            async with httpx.AsyncClient(
                http2=True,
                verify=certifi.where(),
                follow_redirects=False,
                trust_env=False,
                timeout=timeout,
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "Authorization": f"Bearer {service_key}",
                        "Content-Type": "application/json; charset=utf-8",
                        "User-Agent": "AskCrump-ConnectedReleasePreview/1",
                        "apikey": service_key,
                    },
                    json=payload,
                ) as response:
                    declared = response.headers.get("content-length")
                    if declared is not None:
                        try:
                            if not 0 <= int(declared) <= _MAX_RESPONSE_BYTES:
                                raise ValueError
                        except ValueError:
                            raise ConnectedReleasePreviewDatabaseError() from None
                    collected = bytearray()
                    async for chunk in response.aiter_bytes():
                        collected.extend(chunk)
                        if len(collected) > _MAX_RESPONSE_BYTES:
                            raise ConnectedReleasePreviewDatabaseError()
                    body = bytes(collected)
                    status_code = response.status_code
                    content_type = response.headers.get("content-type", "")
        except httpx.HTTPError:
            raise ConnectedReleasePreviewDatabaseError() from None
        if (
            status_code != 200
            or not body
            or len(body) > _MAX_RESPONSE_BYTES
            or content_type.split(";", 1)[0].casefold()
            not in {"application/json", "text/json"}
        ):
            raise ConnectedReleasePreviewDatabaseError()
        try:
            return json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=lambda _item: (_ for _ in ()).throw(ValueError()),
            )
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
            raise ConnectedReleasePreviewDatabaseError() from None

    def __repr__(self) -> str:
        return "ConnectedReleasePreviewProductionDatabase(authority='service-role')"


__all__ = [
    "ConnectedReleasePreviewDatabaseError",
    "ConnectedReleasePreviewProductionDatabase",
]
