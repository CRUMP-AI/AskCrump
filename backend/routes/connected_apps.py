"""Truthful, source-locked HTTP boundary for owner-connected applications.

The status route reports ready only when the source/environment lock and an
injected, fresh composition attestation agree. An environment-disabled build
returns before authentication; an enabled build authenticates before acquiring
its secret-bound request graph or invoking a control-plane dependency. The
checked-in source lock remains false.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from .. import config
from ..auth_service import (
    EXPECTED_OWNER_HEADER,
    AuthenticatedUser,
    AuthenticationError,
    authenticate_request,
)
from ..connected_app_background import (
    ConnectedBackgroundCycle,
    ConnectedBackgroundError,
    ConnectedOperatorBackgroundSupervisor,
)
from ..connected_app_multi_step import (
    ConnectedMultiStepError,
    ConnectedMultiStepPublicRecord,
)
from ..connected_app_multi_step_adapters import ConnectedMultiStepAdapterError
from ..connected_app_service import (
    ConnectedAppService,
    ConnectedAppServiceError,
    ConnectedScheduleStatus,
    parse_account_kind,
    parse_action,
    parse_actions,
    parse_approval_decision,
    parse_provider,
    parse_resource,
    parse_schedule_status,
    schedule_transition_allowed,
)
from ..connected_app_read_surface import (
    ConnectedOwnerReadResultError,
    ConnectedOwnerReadResultService,
)
from ..runtime import db, settings


router = APIRouter(prefix="/api/connected-apps", tags=["connected-apps"])
cron_router = APIRouter(tags=["cron"])

# Deliberately uncomposed at import time. A separately reviewed production
# factory may inject this only after the durable schema, credential broker,
# OAuth flows, provider adapters, scheduler, action runtime, and readiness
# source agree.
connected_app_service: ConnectedAppService | None = None
connected_read_result_service: ConnectedOwnerReadResultService | None = None
connected_background_worker: ConnectedOperatorBackgroundSupervisor | None = None
connected_multi_step_worker: object | None = None

_MAX_BODY_BYTES = 16_384
_NO_STORE = {"Cache-Control": "private, no-store"}
_CRON_NO_STORE = {"Cache-Control": "no-store"}
_CRON_CYCLE_TIMEOUT_SECONDS = 240.0
_CONTROL = frozenset(chr(value) for value in (*range(32), 127))
_RELEASE_PREVIEW_CONFIRMATION = (
    "RUN_CONNECTED_RELEASE_PREVIEW_WITH_DEDICATED_NON_CUSTOMER_ACCOUNTS"
)
_RELEASE_PREVIEW_CSRF = "connected-release-preview-v1"
_RELEASE_PREVIEW_ORIGINS = frozenset(
    {"https://askcrump.com", "https://www.askcrump.com"}
)
_T = TypeVar("_T")


async def _acquire_request_activation(assertion_source: Callable[[], object]) -> object:
    """Import activation only after authentication succeeds.

    The production activation host installs this router while composing the
    connected graph. A module-level import would create a routes -> request
    activation -> production activation -> routes cycle. Keeping this import
    local also preserves the release-off guarantee that application import is
    inert with respect to connected secrets and graph dependencies.
    """

    from ..connected_app_request_activation import acquire_connected_request_activation

    return await acquire_connected_request_activation(assertion_source)


def _response(content: dict[str, object], status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content, headers=_NO_STORE)


def _cron_response(content: dict[str, object], status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content, headers=_CRON_NO_STORE)


def _cron_error(code: str, status_code: int, *, retryable: bool) -> JSONResponse:
    return _cron_response(
        {"success": False, "code": code, "retryable": retryable},
        status_code,
    )


def _not_ready_status() -> JSONResponse:
    return JSONResponse(
        content={
            "success": True,
            "enabled": False,
            "status": "not_ready",
            "providers": [],
            "capabilities": [],
        },
        headers=_NO_STORE,
    )


def _cron_authorized(request: Request) -> bool:
    secret = getattr(settings, "cron_secret", None)
    if not isinstance(secret, str) or not secret:
        return False
    authorization = request.headers.get("authorization", "")
    try:
        return hmac.compare_digest(authorization, f"Bearer {secret}")
    except TypeError:
        return False


async def _run_connected_background_cycle() -> JSONResponse:
    worker = connected_background_worker
    if worker is None or worker.external_wake is not True or not worker.running:
        return _cron_error("CONNECTED_BACKGROUND_NOT_READY", 503, retryable=True)
    try:
        cycle = await asyncio.wait_for(
            worker.run_cycle(),
            timeout=_CRON_CYCLE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return _cron_error("CONNECTED_BACKGROUND_TIMEOUT", 503, retryable=True)
    except ConnectedBackgroundError:
        return _cron_error("CONNECTED_BACKGROUND_NOT_READY", 503, retryable=True)
    except Exception:
        return _cron_error("CONNECTED_BACKGROUND_UNAVAILABLE", 503, retryable=True)
    if type(cycle) is not ConnectedBackgroundCycle:
        return _cron_error("CONNECTED_BACKGROUND_INVALID", 503, retryable=True)
    failed = (
        cycle.dispatch_failed
        or cycle.scheduler_failed
        or cycle.cleanup_failed
        or cycle.oauth_expiry_failed
        or cycle.reconciliation_failed
        or cycle.continuation_failed
        or cycle.retention_failed
    )
    return _cron_response(
        {
            "success": not failed,
            "dispatchOwnersScanned": cycle.dispatch_owners_scanned,
            "dispatchActionsConsidered": cycle.dispatch_actions_considered,
            "dispatchActionsInvoked": cycle.dispatch_actions_invoked,
            "dispatchTerminalCount": cycle.dispatch_terminal_count,
            "scheduleCompletionCount": cycle.schedule_completion_count,
            "cleanupAttempts": cycle.cleanup_attempts,
            "cleanupTerminalCount": cycle.cleanup_terminal_count,
            "expiredOAuthFlowCount": cycle.expired_oauth_flow_count,
            "expiredOAuthProvisionalCount": cycle.expired_oauth_provisional_count,
            "continuationCandidatesConsidered": (
                cycle.continuation_candidates_considered
            ),
            "continuationClaimsAcquired": cycle.continuation_claims_acquired,
            "continuationTerminalCount": cycle.continuation_terminal_count,
            "continuationFailedCount": cycle.continuation_failed_count,
            "expiredPayloadsPurged": cycle.expired_payloads_purged,
            "expiredPlansPurged": cycle.expired_plans_purged,
            "expiredLoopEnvelopesPurged": cycle.expired_loop_envelopes_purged,
            "dispatchFailed": cycle.dispatch_failed,
            "schedulerFailed": cycle.scheduler_failed,
            "cleanupFailed": cycle.cleanup_failed,
            "oauthExpiryFailed": cycle.oauth_expiry_failed,
            "reconciliationFailed": cycle.reconciliation_failed,
            "continuationFailed": cycle.continuation_failed,
            "retentionFailed": cycle.retention_failed,
        },
        503 if failed else 200,
    )


@cron_router.get("/api/cron/connected-apps")
async def connected_app_worker_cron(request: Request) -> JSONResponse:
    """Run one bounded, database-fenced worker cycle on a Vercel cron wake."""

    # Authenticate before revealing any release or readiness state. Vercel
    # invokes configured cron jobs with GET and this exact bearer credential.
    if not _cron_authorized(request):
        return _cron_error("CONNECTED_WORKER_UNAUTHORIZED", 401, retryable=False)
    if (
        config.connected_apps_release_candidate_source_released() is not True
        or getattr(settings, "connected_apps_enabled", False) is not True
        or getattr(settings, "is_production", False) is not True
    ):
        return _cron_error("CONNECTED_APPS_NOT_RELEASED", 404, retryable=False)
    try:
        lease = await _acquire_request_activation(
            lambda: request.headers.get("x-vercel-oidc-token")
        )
    except Exception:
        return _cron_error("CONNECTED_BACKGROUND_UNAVAILABLE", 503, retryable=True)
    response = await _run_connected_background_cycle()
    try:
        if lease is not None:
            await lease.release()
    except Exception:
        return _cron_error("CONNECTED_BACKGROUND_UNAVAILABLE", 503, retryable=True)
    return response


def _error(exc: ConnectedAppServiceError) -> JSONResponse:
    return _response(
        {"success": False, "code": exc.code, "retryable": exc.retryable},
        exc.status_code,
    )


def _multi_step_error(exc: ConnectedMultiStepError | ConnectedMultiStepAdapterError) -> JSONResponse:
    code = exc.code
    if code in {"CONNECTED_MULTI_STEP_INVALID", "CONNECTED_MULTI_STEP_UNAUTHORIZED"}:
        status_code, retryable = 404, False
    elif code in {
        "CONNECTED_MULTI_STEP_BUSY",
        "CONNECTED_MULTI_STEP_CANCELLED",
        "CONNECTED_MULTI_STEP_EXPIRED",
        "CONNECTED_MULTI_STEP_LIMIT_REACHED",
    }:
        status_code, retryable = 409, bool(exc.retryable)
    else:
        status_code, retryable = 503, bool(exc.retryable)
    return _error(
        ConnectedAppServiceError(
            code,
            status_code,
            retryable=retryable,
        )
    )


def _authentication_error(exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "authenticated": False,
            "error": exc.message,
            "code": exc.code,
            **dict(exc.details or {}),
        },
        headers=_NO_STORE,
    )


def _active_service() -> ConnectedAppService:
    # Keep this check first. An unreleased build cannot parse or call through to
    # a connected-app dependency.
    if not settings.connected_apps_enabled or connected_app_service is None:
        raise ConnectedAppServiceError("CONNECTED_APPS_NOT_RELEASED", 404)
    connected_app_service.require_ready()
    return connected_app_service


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None
    if str(parsed) != value:
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return value


def _reject_controls(value: object, *, depth: int = 0) -> None:
    if depth > 8:
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    if isinstance(value, str):
        if any(character in _CONTROL for character in value):
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        return
    if isinstance(value, list):
        if len(value) > 32:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        for item in value:
            _reject_controls(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 32:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        for key, item in value.items():
            _reject_controls(key, depth=depth + 1)
            _reject_controls(item, depth=depth + 1)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        result[key] = value
    return result


async def _body(
    request: Request,
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    raw_length = request.headers.get("content-length")
    if raw_length:
        try:
            length = int(raw_length)
        except ValueError:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None
        if length < 0 or length > _MAX_BODY_BYTES:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    raw = await request.body()
    if not raw or len(raw) > _MAX_BODY_BYTES:
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
        )
    except ConnectedAppServiceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400) from None
    if not isinstance(value, dict):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    _reject_controls(value)
    return value


def _string(value: object, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or value != value.strip():
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return value


def _integer(value: object, *, minimum: int = 1, maximum: int = 2_678_400) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
    return value


def _optional_string(value: object, *, maximum: int = 2048) -> str | None:
    if value is None:
        return None
    return _string(value, maximum=maximum)


async def _owner(request: Request) -> tuple[str, str]:
    authenticated: AuthenticatedUser = await authenticate_request(
        request,
        db,
        settings,
        require_account=True,
        require_expected_owner_header=True,
    )
    owner_id = _canonical_uuid(authenticated.user.get("id"))
    session_id = _canonical_uuid(authenticated.session.get("id"))
    if request.headers.get(EXPECTED_OWNER_HEADER) != owner_id:
        raise ConnectedAppServiceError("CONNECTED_OWNER_MISMATCH", 403)
    return owner_id, session_id


def _release_preview_same_origin(request: Request) -> bool:
    """Require browser-authored same-origin metadata for the one-shot ceremony."""

    host = request.headers.get("host", "").strip().lower()
    origin = request.headers.get("origin", "").strip().lower()
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    csrf = request.headers.get("x-ask-crump-release-preview-csrf", "")
    expected_origin = f"https://{host}"
    return bool(
        expected_origin in _RELEASE_PREVIEW_ORIGINS
        and origin == expected_origin
        and fetch_site == "same-origin"
        and hmac.compare_digest(csrf, _RELEASE_PREVIEW_CSRF)
    )


def _release_preview_session_binding(session_id: str) -> str:
    canonical = _canonical_uuid(session_id)
    return hashlib.sha256(
        b"askcrump.connected-release-session/v1\0" + canonical.encode("ascii")
    ).hexdigest()


async def _run(factory: Callable[[], Awaitable[_T]]) -> _T | JSONResponse:
    try:
        return await factory()
    except ConnectedAppServiceError as exc:
        return _error(exc)
    except ConnectedOwnerReadResultError as exc:
        return _error(
            ConnectedAppServiceError(
                exc.code,
                exc.status_code,
                retryable=exc.status_code == 503,
            )
        )
    except (ConnectedMultiStepError, ConnectedMultiStepAdapterError) as exc:
        return _multi_step_error(exc)
    except AuthenticationError:
        raise
    except (TypeError, ValueError):
        return _error(ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400))
    except Exception:
        return _error(ConnectedAppServiceError("CONNECTED_OPERATION_FAILED", 503, retryable=True))


async def _run_owner(
    request: Request,
    factory: Callable[[ConnectedAppService, str, str], Awaitable[_T]],
) -> _T | JSONResponse:
    """Authenticate first, then hold one request-scoped graph lease.

    Vercel supplies its OIDC assertion on every function request.  Reading that
    assertion or invoking KMS before account authentication would let anonymous
    traffic cause secret-bound work.  This boundary keeps the release-off path
    inert and holds the lease through the complete owner operation.
    """

    if (
        config.connected_apps_release_candidate_source_released() is not True
        or getattr(settings, "connected_apps_enabled", False) is not True
    ):
        return _error(ConnectedAppServiceError("CONNECTED_APPS_NOT_RELEASED", 404))

    async def operation() -> _T:
        owner_id, session_id = await _owner(request)
        try:
            lease = await _acquire_request_activation(
                lambda: request.headers.get("x-vercel-oidc-token")
            )
        except Exception:
            raise ConnectedAppServiceError(
                "CONNECTED_APPS_NOT_READY",
                503,
                retryable=True,
            ) from None
        try:
            service = _active_service()
            return await factory(service, owner_id, session_id)
        finally:
            if lease is not None:
                await lease.release()

    return await _run(operation)


def _active_multi_step_worker() -> Any:
    worker = connected_multi_step_worker
    if worker is None:
        raise ConnectedAppServiceError("CONNECTED_MULTI_STEP_NOT_RELEASED", 404)
    if any(
        not callable(getattr(worker, method, None))
        for method in ("list_status", "owner_status", "cancel_owner")
    ):
        raise ConnectedAppServiceError(
            "CONNECTED_MULTI_STEP_NOT_READY",
            503,
            retryable=True,
        )
    return worker


def _public_task(record: object) -> dict[str, object]:
    if type(record) is not ConnectedMultiStepPublicRecord:
        raise ConnectedAppServiceError(
            "CONNECTED_MULTI_STEP_RESULT_INVALID",
            503,
            retryable=True,
        )
    value = record.public()
    if not isinstance(value, dict):
        raise ConnectedAppServiceError(
            "CONNECTED_MULTI_STEP_RESULT_INVALID",
            503,
            retryable=True,
        )
    return value


@router.post("/internal/release-preview", include_in_schema=False)
async def connected_app_internal_release_preview(request: Request) -> JSONResponse:
    """Run one same-deployment, source-pinned release-preview ceremony.

    This boundary deliberately bypasses the normal connected-app activation
    graph: readiness does not exist until this exact child succeeds.  The
    checked-in source lock, production runtime, browser-origin metadata,
    authenticated owner/session, durable claim, and Vercel request assertion
    must all agree before a child process can see secret-bound configuration.
    """

    if (
        config.connected_apps_release_candidate_source_released() is not True
        or getattr(settings, "connected_apps_enabled", False) is not True
        or getattr(settings, "is_production", False) is not True
    ):
        return _error(
            ConnectedAppServiceError(
                "CONNECTED_RELEASE_PREVIEW_NOT_RELEASED",
                404,
            )
        )
    if not _release_preview_same_origin(request):
        return _error(
            ConnectedAppServiceError(
                "CONNECTED_RELEASE_PREVIEW_ORIGIN_REJECTED",
                403,
            )
        )
    try:
        owner_id, session_id = await _owner(request)
    except AuthenticationError as exc:
        return _authentication_error(exc)
    except ConnectedAppServiceError as exc:
        return _error(exc)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        return _error(ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400))
    try:
        value = await _body(request, required=frozenset({"confirmation"}))
        confirmation = _string(value.get("confirmation"), maximum=96)
        if not hmac.compare_digest(confirmation, _RELEASE_PREVIEW_CONFIRMATION):
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        raw_assertion = request.headers.get("x-vercel-oidc-token", "")
        if not isinstance(raw_assertion, str) or not raw_assertion:
            raise ConnectedAppServiceError(
                "CONNECTED_RELEASE_PREVIEW_UNAVAILABLE",
                503,
                retryable=True,
            )

        # Keep release-only modules out of the import path while the source
        # lock is false.  In particular, this route must not acquire the
        # ordinary request activation graph before readiness exists.
        from ..connected_app_kms import ConnectedVercelOIDCAssertion
        from ..connected_app_release_preview_supervisor import (
            claim_connected_release_preview_ceremony,
            run_connected_release_preview_child,
        )

        assertion = ConnectedVercelOIDCAssertion(raw_assertion)
        claim = await claim_connected_release_preview_ceremony(
            owner_id=owner_id,
            session_binding_sha256=_release_preview_session_binding(session_id),
            confirmation=confirmation,
        )
        result = await run_connected_release_preview_child(
            assertion=assertion,
            invocation_id=claim.invocation_id,
            issued_at=claim.issued_at,
            expires_at=claim.expires_at,
            confirmation=confirmation,
            recovery=claim.recovery,
        )
    except ConnectedAppServiceError as exc:
        return _error(exc)
    except Exception:
        return _error(
            ConnectedAppServiceError(
                "CONNECTED_RELEASE_PREVIEW_FAILED",
                503,
                retryable=True,
            )
        )
    return _response(
        {
            "success": True,
            "status": "completed",
            "invocationId": result.invocation_id,
            "checkedAt": result.checked_at.isoformat().replace("+00:00", "Z"),
            "expiresAt": result.expires_at.isoformat().replace("+00:00", "Z"),
        }
    )


@router.get("/status")
async def connected_app_status(request: Request) -> JSONResponse:
    """Return only content-free release state for the authenticated owner."""

    try:
        authenticated = await authenticate_request(
            request,
            db,
            settings,
            require_account=True,
            require_expected_owner_header=True,
        )
    except AuthenticationError as exc:
        return _authentication_error(exc)
    authenticated_owner = _canonical_uuid(authenticated.user.get("id"))
    if request.headers.get(EXPECTED_OWNER_HEADER) != authenticated_owner:
        return _authentication_error(
            AuthenticationError(
                "The account precondition did not match.",
                status_code=409,
                code="AUTH_OWNER_MISMATCH",
            )
        )
    if (
        config.connected_apps_release_candidate_source_released() is True
        and settings.connected_apps_enabled
    ):
        try:
            lease = await _acquire_request_activation(
                lambda: request.headers.get("x-vercel-oidc-token")
            )
        except Exception:
            return _not_ready_status()
        response = _not_ready_status()
        try:
            service = connected_app_service
            if service is None:
                raise ConnectedAppServiceError("CONNECTED_APPS_NOT_READY", 503)
            manifest = service.public_readiness_manifest()
            response = JSONResponse(
                content={
                    "success": True,
                    "enabled": True,
                    "status": "ready",
                    **manifest,
                },
                headers=_NO_STORE,
            )
        except Exception:
            # Readiness is an availability boundary, not a diagnostic surface.
            # A stale/malformed composition remains hidden and inert.
            response = _not_ready_status()
        try:
            if lease is not None:
                await lease.release()
        except Exception:
            return _not_ready_status()
        return response
    return JSONResponse(
        content={
            "success": True,
            # This endpoint is only an inert discovery shell. A future source
            # release and environment switch are necessary but not sufficient
            # to prove that OAuth, the credential broker, durable storage,
            # provider adapters, and the action runtime are composed and ready.
            # Keep the public answer false until source release, environment
            # enablement, production composition, and its exact readiness
            # attestation all agree.
            "enabled": False,
            "status": "not_released",
            "providers": [],
            "capabilities": [],
        },
        headers=_NO_STORE,
    )


@router.get("/connections")
async def list_connections(request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        records = await service.list_connections(owner_id=owner_id)
        return _response({"success": True, "connections": [item.public() for item in records]})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.post("/oauth/start")
async def start_oauth(request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        session_id: str,
    ) -> JSONResponse:
        value = await _body(
            request,
            required=frozenset(
                {
                    "requestId",
                    "provider",
                    "resource",
                    "accountKind",
                    "actions",
                    "redirectUri",
                    "confirmed",
                }
            ),
            optional=frozenset({"connectionId"}),
        )
        record = await service.start_oauth(
            request_id=_canonical_uuid(value["requestId"]),
            owner_id=owner_id,
            session_id=session_id,
            provider=parse_provider(value["provider"]),
            resource=parse_resource(value["resource"]),
            account_kind=parse_account_kind(value["accountKind"]),
            actions=parse_actions(value["actions"]),
            redirect_uri=_string(value["redirectUri"]),
            connection_id=(
                _canonical_uuid(value["connectionId"])
                if value.get("connectionId") is not None
                else None
            ),
            confirmed=_boolean(value["confirmed"]),
        )
        return _response({"success": True, "authorization": record.public()})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/oauth/callback/{provider}")
async def oauth_callback(provider: str, request: Request) -> Response:
    marker = "failed"
    lease = None
    try:
        if getattr(settings, "connected_apps_enabled", False) is not True:
            raise ConnectedAppServiceError("CONNECTED_APPS_NOT_RELEASED", 404)
        parsed_provider = parse_provider(provider)
        pairs = list(request.query_params.multi_items())
        if not 2 <= len(pairs) <= 8:
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
        if len({key for key, _ in pairs}) != len(pairs):
            raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
        values = dict(pairs)
        _reject_controls(values)
        common_error = {"error", "error_description", "error_uri", "state"}
        optional = (
            {"scope", "authuser", "prompt", "hd"}
            if parsed_provider.value == "google"
            else {"session_state", "client_info"}
        )
        keys = set(values)
        access_denied = False
        if "error" in keys:
            if "code" in keys or not {"error", "state"}.issubset(keys) or not keys.issubset(common_error):
                raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
            _string(values["state"], maximum=256)
            if _string(values["error"], maximum=256) != "access_denied":
                raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
            if "error_description" in values:
                _string(values["error_description"], maximum=2048)
            if "error_uri" in values:
                _string(values["error_uri"], maximum=2048)
            access_denied = True
        else:
            if not {"code", "state"}.issubset(keys) or not keys.issubset(
                {"code", "state"} | optional
            ):
                raise ConnectedAppServiceError("CONNECTED_OAUTH_CALLBACK_INVALID", 400)
            for key in optional & keys:
                _string(values[key], maximum=2048)
        authenticated: AuthenticatedUser = await authenticate_request(
            request,
            db,
            settings,
            require_account=True,
            require_expected_owner_header=False,
        )
        owner_id = _canonical_uuid(authenticated.user.get("id"))
        session_id = _canonical_uuid(authenticated.session.get("id"))
        lease = await _acquire_request_activation(
            lambda: request.headers.get("x-vercel-oidc-token")
        )
        service = _active_service()
        if access_denied:
            await service.deny_oauth_callback(
                owner_id=owner_id,
                session_id=session_id,
                provider=parsed_provider,
                state=_string(values["state"], maximum=256),
                error="access_denied",
            )
            marker = "denied"
        else:
            await service.complete_oauth_callback(
                owner_id=owner_id,
                session_id=session_id,
                provider=parsed_provider,
                code=_string(values["code"], maximum=4096),
                state=_string(values["state"], maximum=256),
            )
            marker = "connected"
    except Exception:
        # OAuth query values are bearer-like, untrusted secrets.  Even a
        # malformed, unavailable, or failed callback must leave the callback
        # URL immediately; never render an error document at the raw URL.
        marker = "failed"
    finally:
        if lease is not None:
            try:
                await lease.release()
            except Exception:
                marker = "failed"
    return RedirectResponse(
        url=f"/app?connected-app={marker}",
        status_code=303,
        headers=_NO_STORE,
    )


@router.post("/connections/{connection_id}/disconnect")
async def disconnect(connection_id: str, request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        session_id: str,
    ) -> JSONResponse:
        value = await _body(request, required=frozenset({"requestId", "confirmed"}))
        record = await service.disconnect(
            request_id=_canonical_uuid(value["requestId"]),
            owner_id=owner_id,
            session_id=session_id,
            connection_id=_canonical_uuid(connection_id),
            confirmed=_boolean(value["confirmed"]),
        )
        return _response({"success": True, "disconnection": record.public()})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/schedules")
async def list_schedules(request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        records = await service.list_schedules(owner_id=owner_id)
        return _response({"success": True, "schedules": [item.public() for item in records]})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.post("/schedules/{schedule_id}/{target}")
async def transition_schedule(schedule_id: str, target: str, request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        session_id: str,
    ) -> JSONResponse:
        targets = {
            "pause": ConnectedScheduleStatus.PAUSED,
            "resume": ConnectedScheduleStatus.ACTIVE,
            "cancel": ConnectedScheduleStatus.CANCELLED,
        }
        if target not in targets:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        value = await _body(
            request,
            required=frozenset(
                {
                    "requestId",
                    "expectedTaskStateRevision",
                    "expectedStatus",
                    "confirmed",
                }
            ),
        )
        expected_status = parse_schedule_status(value["expectedStatus"])
        if not schedule_transition_allowed(expected_status, targets[target]):
            raise ConnectedAppServiceError("CONNECTED_SCHEDULE_TRANSITION_INVALID", 409)
        record = await service.transition_schedule(
            request_id=_canonical_uuid(value["requestId"]),
            owner_id=owner_id,
            session_id=session_id,
            schedule_id=_canonical_uuid(schedule_id),
            expected_task_state_revision=_integer(
                value["expectedTaskStateRevision"], maximum=2_147_483_647
            ),
            expected_status=expected_status,
            target=targets[target],
            confirmed=_boolean(value["confirmed"]),
        )
        return _response({"success": True, "schedule": record.public()})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/tasks")
async def list_tasks(request: Request) -> JSONResponse:
    async def operation(
        _service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        if request.query_params:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        records = await _active_multi_step_worker().list_status(
            owner_id=owner_id,
            limit=50,
        )
        if not isinstance(records, tuple) or len(records) > 50:
            raise ConnectedAppServiceError(
                "CONNECTED_MULTI_STEP_RESULT_INVALID",
                503,
                retryable=True,
            )
        return _response(
            {
                "success": True,
                "tasks": [_public_task(item) for item in records],
            }
        )

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/tasks/{loop_id}")
async def task_status(loop_id: str, request: Request) -> JSONResponse:
    async def operation(
        _service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        if request.query_params:
            raise ConnectedAppServiceError("CONNECTED_INPUT_INVALID", 400)
        record = await _active_multi_step_worker().owner_status(
            owner_id=owner_id,
            loop_id=_canonical_uuid(loop_id),
        )
        return _response({"success": True, "task": _public_task(record)})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.post("/tasks/{loop_id}/cancel")
async def cancel_task(loop_id: str, request: Request) -> JSONResponse:
    async def operation(
        _service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        value = await _body(
            request,
            required=frozenset({"taskStateRevision", "confirmed"}),
        )
        if _boolean(value["confirmed"]) is not True:
            raise ConnectedAppServiceError("CONNECTED_USER_ACTION_REQUIRED", 400)
        record = await _active_multi_step_worker().cancel_owner(
            owner_id=owner_id,
            loop_id=_canonical_uuid(loop_id),
            expected_revision=_integer(
                value["taskStateRevision"],
                maximum=2_147_483_647,
            ),
        )
        return _response({"success": True, "task": _public_task(record)})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/actions")
async def list_actions(request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        records = await service.list_actions(owner_id=owner_id)
        return _response({"success": True, "actions": [item.public() for item in records]})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/actions/{action_id}")
async def action_status(action_id: str, request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        record = await service.get_action(owner_id=owner_id, action_id=_canonical_uuid(action_id))
        return _response({"success": True, "action": record.public()})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/results/{result_reference_id}")
async def connected_read_result(
    result_reference_id: str,
    request: Request,
) -> JSONResponse:
    """Open one settled encrypted read result for its authenticated owner."""

    async def operation(
        _service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        # _run_owner has already authenticated and required the exact service
        # readiness once under the request lease. Do not repeat the potentially
        # time-sensitive readiness probe inside the same operation.
        read_results = connected_read_result_service
        if read_results is None:
            raise ConnectedAppServiceError("CONNECTED_APPS_NOT_READY", 503)
        record = await read_results.get(
            owner_id=owner_id,
            result_reference_id=_canonical_uuid(result_reference_id),
        )
        return _response({"success": True, "result": record})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.get("/approvals")
async def list_approvals(request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        _session_id: str,
    ) -> JSONResponse:
        records = await service.list_approvals(owner_id=owner_id)
        return _response({"success": True, "approvals": [item.public() for item in records]})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result


@router.post("/approvals/{approval_id}")
async def decide_approval(approval_id: str, request: Request) -> JSONResponse:
    async def operation(
        service: ConnectedAppService,
        owner_id: str,
        session_id: str,
    ) -> JSONResponse:
        value = await _body(
            request,
            required=frozenset(
                {
                    "decisionId",
                    "actionId",
                    "connectionId",
                    "taskId",
                    "turnId",
                    "provider",
                    "resource",
                    "action",
                    "authorizationRevision",
                    "authorizationSnapshotSha256",
                    "grantedScopesSha256",
                    "policyVersion",
                    "actionRevision",
                    "approvalBindingSha256",
                    "parametersSha256",
                    "resourceVersionSha256",
                    "previewSha256",
                    "decision",
                    "confirmed",
                }
            ),
        )
        record = await service.decide_approval(
            decision_id=_canonical_uuid(value["decisionId"]),
            owner_id=owner_id,
            session_id=session_id,
            approval_id=_canonical_uuid(approval_id),
            action_id=_canonical_uuid(value["actionId"]),
            connection_id=_canonical_uuid(value["connectionId"]),
            task_id=_canonical_uuid(value["taskId"]),
            turn_id=_canonical_uuid(value["turnId"]),
            provider=parse_provider(value["provider"]),
            resource=parse_resource(value["resource"]),
            action=parse_action(value["action"]),
            authorization_revision=_integer(value["authorizationRevision"], maximum=2_147_483_647),
            authorization_snapshot_sha256=_string(value["authorizationSnapshotSha256"], maximum=64),
            granted_scopes_sha256=_string(value["grantedScopesSha256"], maximum=64),
            policy_version=_string(value["policyVersion"], maximum=128),
            action_revision=_integer(value["actionRevision"], maximum=2_147_483_647),
            approval_binding_sha256=_string(value["approvalBindingSha256"], maximum=64),
            parameters_sha256=_string(value["parametersSha256"], maximum=64),
            resource_version_sha256=_optional_string(value["resourceVersionSha256"], maximum=64),
            preview_sha256=_string(value["previewSha256"], maximum=64),
            decision=parse_approval_decision(value["decision"]),
            confirmed=_boolean(value["confirmed"]),
        )
        return _response({"success": True, "approval": record.public()})

    result = await _run_owner(request, operation)
    assert isinstance(result, JSONResponse)
    return result
