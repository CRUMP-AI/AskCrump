"""Provider adapters for Ask Crump video generation.

Provider-specific authentication, request payloads, polling, failure semantics,
and output retrieval live here so the product layer can remain provider-agnostic.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .config import Settings


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RUNWAY_BASE_URL = "https://api.dev.runwayml.com/v1"
GEMINI_ALLOWED_VIDEO_HOST_SUFFIXES = (".googleapis.com", ".googleusercontent.com")
VIDEO_DOWNLOAD_REDIRECTS = frozenset({301, 302, 303, 307, 308})
VIDEO_DOWNLOAD_MAX_REDIRECTS = 3
logger = logging.getLogger("askcrump.video.providers")


def _safe_log_token(value: Any, *, limit: int = 120) -> str:
    raw = str(value or "")[:limit]
    return "".join(character if character.isalnum() or character in "._-" else "_" for character in raw)


@dataclass(slots=True)
class ProviderError(RuntimeError):
    message: str
    code: str = "VIDEO_PROVIDER_ERROR"
    status_code: int = 502
    retryable: bool = False
    failure_code: str | None = None
    refund_eligible: bool = True
    acceptance_unknown: bool = False

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


def _safe_https_url(uri: str, *, provider: str) -> str:
    parsed = urlparse(str(uri or ""))
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ProviderError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502) from exc
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or port not in {None, 443}
    ):
        raise ProviderError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502)
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ProviderError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
        raise ProviderError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502)
    if provider == "gemini":
        if host == "generativelanguage.googleapis.com" or any(host.endswith(suffix) for suffix in GEMINI_ALLOWED_VIDEO_HOST_SUFFIXES):
            return uri
        raise ProviderError("Unexpected Gemini video download host.", "UNSAFE_VIDEO_URI", 502)
    return uri


async def _safe_resolved_https_url(uri: str, *, provider: str) -> str:
    """Validate the URL and reject hosts resolving to non-public networks."""
    safe_uri = _safe_https_url(uri, provider=provider)
    host = str(urlparse(safe_uri).hostname or "")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            443,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ProviderError(
            "The video finished but Ask Crump could not resolve its download location.",
            "VIDEO_DOWNLOAD_FAILED",
            503,
            True,
        ) from exc
    resolved = {
        str(item[4][0]).split("%", 1)[0]
        for item in addresses
        if len(item) > 4 and item[4]
    }
    if not resolved:
        raise ProviderError(
            "The video finished but Ask Crump could not resolve its download location.",
            "VIDEO_DOWNLOAD_FAILED",
            503,
            True,
        )
    for value in resolved:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ProviderError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502) from exc
        if not address.is_global:
            raise ProviderError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502)
    return safe_uri


def _url_origin(uri: str) -> tuple[str, str, int]:
    parsed = urlparse(uri)
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ProviderError("Unsafe video download location.", "UNSAFE_VIDEO_URI", 502) from exc
    return parsed.scheme, str(parsed.hostname or "").lower(), port


async def _bounded_provider_download(
    uri: str,
    *,
    provider: str,
    max_bytes: int,
    credential_headers: dict[str, str] | None = None,
) -> bytes:
    """Download with per-hop URL checks, bounded redirects, and streaming cap."""
    limit = max(1, int(max_bytes or 0))
    current_uri = str(uri or "").strip()
    credential_origin = (
        _url_origin(_safe_https_url(current_uri, provider=provider))
        if credential_headers
        else None
    )
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=20.0),
            follow_redirects=False,
        ) as client:
            for hop in range(VIDEO_DOWNLOAD_MAX_REDIRECTS + 1):
                safe_uri = await _safe_resolved_https_url(current_uri, provider=provider)
                headers = (
                    dict(credential_headers or {})
                    if credential_origin and _url_origin(safe_uri) == credential_origin
                    else {}
                )
                async with client.stream("GET", safe_uri, headers=headers) as response:
                    if response.status_code in VIDEO_DOWNLOAD_REDIRECTS:
                        location = str(response.headers.get("location") or "").strip()
                        if not location or hop >= VIDEO_DOWNLOAD_MAX_REDIRECTS:
                            raise ProviderError(
                                "The video download redirected unexpectedly.",
                                "UNSAFE_VIDEO_URI",
                                502,
                            )
                        current_uri = urljoin(safe_uri, location)
                        continue
                    if response.status_code >= 400:
                        raise ProviderError(
                            "The video finished but Ask Crump could not retrieve the file.",
                            "VIDEO_DOWNLOAD_FAILED",
                            503,
                            True,
                        )
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > limit:
                                raise ProviderError(
                                    "The generated video exceeded Ask Crump's storage safety limit.",
                                    "VIDEO_FILE_TOO_LARGE",
                                    502,
                                )
                        except ValueError:
                            pass
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > limit:
                            raise ProviderError(
                                "The generated video exceeded Ask Crump's storage safety limit.",
                                "VIDEO_FILE_TOO_LARGE",
                                502,
                            )
                        data.extend(chunk)
                    if not data:
                        raise ProviderError(
                            "The video provider returned an empty file.",
                            "VIDEO_DOWNLOAD_FAILED",
                            502,
                        )
                    return bytes(data)
    except ProviderError:
        raise
    except httpx.HTTPError as exc:
        raise ProviderError(
            "The video finished but Ask Crump could not retrieve the file.",
            "VIDEO_DOWNLOAD_FAILED",
            503,
            True,
        ) from exc
    raise ProviderError("The video download redirected unexpectedly.", "UNSAFE_VIDEO_URI", 502)


class GeminiVeoProvider:
    provider = "gemini"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.gemini_api_key and self.settings.video_generation_enabled)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": str(self.settings.gemini_api_key or ""),
            "Content-Type": "application/json",
        }

    @staticmethod
    def _provider_error(response: httpx.Response) -> tuple[str, str]:
        code = ""
        message = ""
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                code = str(error.get("status") or error.get("code") or "")[:120]
                message = " ".join(str(error.get("message") or "").split())[:500]
        except (TypeError, ValueError):
            message = " ".join(response.text.split())[:500]
        return code, message

    @classmethod
    def _exception(cls, response: httpx.Response, *, checking: bool = False) -> ProviderError:
        provider_code, provider_message = cls._provider_error(response)
        acceptance_unknown = not checking and response.status_code >= 500
        request_id = str(response.headers.get("x-request-id") or response.headers.get("x-goog-request-id") or "")[:160]
        logger.error(
            "Gemini video request rejected phase=%s status=%s code=%s request_id=%s",
            "poll" if checking else "start",
            response.status_code,
            _safe_log_token(provider_code) or "-",
            _safe_log_token(request_id, limit=160) or "-",
        )
        diagnostic = f"{provider_code} {provider_message}".lower()
        if response.status_code in {401, 403} or "permission_denied" in diagnostic:
            return ProviderError(
                "Gemini video access is not enabled for this API key or project.",
                "VIDEO_PROVIDER_PERMISSION_REQUIRED",
                503,
                acceptance_unknown=acceptance_unknown,
            )
        if "quota" in diagnostic or "billing" in diagnostic or "resource_exhausted" in diagnostic:
            return ProviderError(
                "The Gemini video provider project has no available quota or billing budget.",
                "VIDEO_PROVIDER_QUOTA_REQUIRED",
                503,
                acceptance_unknown=acceptance_unknown,
            )
        if response.status_code == 429:
            return ProviderError("The video provider is rate limited. Try again shortly.", "VIDEO_RATE_LIMIT", 429, True)
        return ProviderError(
            (
                "The video provider could not return job status."
                if checking
                else (
                    "Could not confirm whether the video provider accepted "
                    "the generation request."
                    if acceptance_unknown
                    else "The video provider rejected the generation request."
                )
            ),
            (
                "VIDEO_STATUS_UNAVAILABLE"
                if checking
                else (
                    "VIDEO_PROVIDER_UNAVAILABLE"
                    if acceptance_unknown
                    else "VIDEO_PROVIDER_REJECTED"
                )
            ),
            502,
            response.status_code >= 500,
            failure_code=provider_code or None,
            acceptance_unknown=acceptance_unknown,
        )

    async def start(
        self,
        *,
        model: str,
        prompt: str,
        aspect_ratio: str,
        resolution: str,
        duration_seconds: int = 8,
        video_reference: str | None = None,
        initial_image: dict[str, str] | None = None,
        reference_images: list[dict[str, str]] | None = None,
    ) -> str:
        if not self.enabled:
            raise ProviderError("Gemini video generation is not configured.", "VIDEO_NOT_CONFIGURED", 503)

        instance: dict[str, Any] = {"prompt": prompt}
        parameters: dict[str, Any] = {
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
            "durationSeconds": duration_seconds,
        }
        if video_reference:
            instance["video"] = {"uri": video_reference}
            # Veo 3.1 Fast rejects numberOfVideos on extension requests.
            # Extension inherently returns a single continued video.
            parameters["resolution"] = "720p"
            parameters["durationSeconds"] = 8
        elif reference_images:
            instance["referenceImages"] = [
                {
                    "image": {
                        "inlineData": {
                            "mimeType": str(reference.get("mimeType") or "image/png"),
                            "data": str(reference.get("data") or ""),
                        },
                    },
                    "referenceType": "asset",
                }
                for reference in reference_images[:3]
            ]
        elif initial_image:
            instance["image"] = {
                "inlineData": {
                    "mimeType": str(initial_image.get("mimeType") or "image/png"),
                    "data": str(initial_image.get("data") or ""),
                },
            }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=15.0)) as client:
                response = await client.post(
                    f"{GEMINI_BASE_URL}/models/{model}:predictLongRunning",
                    headers=self.headers,
                    json={"instances": [instance], "parameters": parameters},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not confirm whether the video provider accepted the generation request.",
                "VIDEO_PROVIDER_UNAVAILABLE",
                503,
                True,
                acceptance_unknown=True,
            ) from exc
        if response.status_code >= 400:
            raise self._exception(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                "The video provider returned an invalid response after launch.",
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                502,
                True,
                acceptance_unknown=True,
            ) from exc
        operation_name = str(body.get("name") or "").strip()
        if not operation_name:
            raise ProviderError(
                "The video provider did not return a job identifier after launch.",
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                502,
                True,
                acceptance_unknown=True,
            )
        return operation_name[:500]

    async def poll(self, provider_job_id: str) -> dict[str, Any]:
        operation_name = str(provider_job_id or "").lstrip("/")
        if not operation_name:
            raise ProviderError("Video job is missing provider state.", "VIDEO_JOB_CORRUPT", 500)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
                response = await client.get(f"{GEMINI_BASE_URL}/{operation_name}", headers=self.headers)
        except httpx.HTTPError as exc:
            raise ProviderError("Could not check video generation status.", "VIDEO_STATUS_UNAVAILABLE", 503, True) from exc
        if response.status_code >= 400:
            raise self._exception(response, checking=True)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError("The video provider returned an invalid status response.", "VIDEO_PROVIDER_INVALID_RESPONSE", 502, True) from exc

        if not body.get("done"):
            return {"status": "processing"}
        if body.get("error"):
            provider_error = body.get("error") or {}
            failure_code = str(provider_error.get("status") or provider_error.get("code") or "")[:120]
            message = str(provider_error.get("message") or "Video generation failed.")[:500]
            return {
                "status": "failed",
                "failureCode": failure_code or None,
                "failureMessage": message,
                # Gemini's current Veo pricing states generation is billed only when
                # the video is successfully generated.
                "refundEligible": True,
            }

        samples = (((body.get("response") or {}).get("generateVideoResponse") or {}).get("generatedSamples") or [])
        sample = samples[0] if samples and isinstance(samples[0], dict) else {}
        uri = str((sample.get("video") or {}).get("uri") or "").strip()
        if not uri:
            return {
                "status": "failed",
                "failureCode": "NO_VIDEO_OUTPUT",
                "failureMessage": "The provider completed without a video file.",
                "refundEligible": True,
            }
        return {
            "status": "ready",
            "outputUrl": _safe_https_url(uri, provider="gemini"),
            "providerAssetReference": uri,
        }

    async def download(self, uri: str, *, max_bytes: int) -> bytes:
        host = str(urlparse(str(uri or "")).hostname or "").lower()
        credentials = (
            {"x-goog-api-key": str(self.settings.gemini_api_key or "")}
            if host == "generativelanguage.googleapis.com"
            else None
        )
        return await _bounded_provider_download(
            uri,
            provider="gemini",
            max_bytes=max_bytes,
            credential_headers=credentials,
        )


class RunwayProvider:
    provider = "runway"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.runway_api_secret and self.settings.video_generation_enabled)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.runway_api_secret or ''}",
            "X-Runway-Version": self.settings.runway_api_version,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                return " ".join(str(body.get("error") or body.get("message") or "").split())[:500]
        except ValueError:
            pass
        return " ".join(response.text.split())[:500]

    @classmethod
    def _exception(cls, response: httpx.Response, *, checking: bool = False) -> ProviderError:
        message = cls._message(response)
        acceptance_unknown = not checking and response.status_code >= 500
        logger.error(
            "Runway video request rejected phase=%s status=%s request_id=%s",
            "poll" if checking else "start",
            response.status_code,
            _safe_log_token(response.headers.get("x-request-id"), limit=160) or "-",
        )
        if response.status_code in {401, 403}:
            return ProviderError(
                "Runway API access is not configured for this project.",
                "VIDEO_PROVIDER_PERMISSION_REQUIRED",
                503,
                acceptance_unknown=acceptance_unknown,
            )
        if response.status_code in {402, 409} or "credit" in message.lower() or "billing" in message.lower():
            return ProviderError(
                "Runway has no available provider credits or billing budget.",
                "VIDEO_PROVIDER_QUOTA_REQUIRED",
                503,
                acceptance_unknown=acceptance_unknown,
            )
        if response.status_code == 429:
            return ProviderError("Runway is rate limited. Try again shortly.", "VIDEO_RATE_LIMIT", 429, True)
        return ProviderError(
            (
                "Runway could not return job status."
                if checking
                else (
                    "Could not confirm whether Runway accepted the generation request."
                    if acceptance_unknown
                    else "Runway rejected the generation request."
                )
            ),
            (
                "VIDEO_STATUS_UNAVAILABLE"
                if checking
                else (
                    "VIDEO_PROVIDER_UNAVAILABLE"
                    if acceptance_unknown
                    else "VIDEO_PROVIDER_REJECTED"
                )
            ),
            502,
            response.status_code >= 500,
            acceptance_unknown=acceptance_unknown,
        )

    async def start(
        self,
        *,
        model: str,
        prompt: str,
        aspect_ratio: str,
        duration_seconds: int,
        prompt_image: str | None = None,
    ) -> str:
        if not self.enabled:
            raise ProviderError("Runway video generation is not configured.", "VIDEO_NOT_CONFIGURED", 503)
        ratio = "1280:720" if aspect_ratio == "16:9" else "720:1280"
        payload = {
            "model": model,
            "promptText": prompt,
            "ratio": ratio,
            "duration": duration_seconds,
        }
        endpoint = "text_to_video"
        if prompt_image:
            payload["promptImage"] = prompt_image
            endpoint = "image_to_video"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=15.0)) as client:
                response = await client.post(f"{RUNWAY_BASE_URL}/{endpoint}", headers=self.headers, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not confirm whether Runway accepted the video request.",
                "VIDEO_PROVIDER_UNAVAILABLE",
                503,
                True,
                acceptance_unknown=True,
            ) from exc
        if response.status_code >= 400:
            raise self._exception(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(
                "Runway returned an invalid response after launch.",
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                502,
                True,
                acceptance_unknown=True,
            ) from exc
        task_id = str(body.get("id") or "").strip()
        if not task_id:
            raise ProviderError(
                "Runway did not return a task identifier after launch.",
                "VIDEO_PROVIDER_INVALID_RESPONSE",
                502,
                True,
                acceptance_unknown=True,
            )
        return task_id[:500]

    async def poll(self, provider_job_id: str) -> dict[str, Any]:
        task_id = str(provider_job_id or "").strip()
        if not task_id:
            raise ProviderError("Video job is missing provider state.", "VIDEO_JOB_CORRUPT", 500)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
                response = await client.get(f"{RUNWAY_BASE_URL}/tasks/{task_id}", headers=self.headers)
        except httpx.HTTPError as exc:
            raise ProviderError("Could not check Runway generation status.", "VIDEO_STATUS_UNAVAILABLE", 503, True) from exc
        if response.status_code >= 400:
            raise self._exception(response, checking=True)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError("Runway returned an invalid status response.", "VIDEO_PROVIDER_INVALID_RESPONSE", 502, True) from exc

        status = str(body.get("status") or "").upper()
        if status in {"PENDING", "RUNNING", "THROTTLED"} or not status:
            return {"status": "processing", "providerStatus": status or "UNKNOWN"}
        if status == "SUCCEEDED":
            outputs = body.get("output") or []
            uri = str(outputs[0] if isinstance(outputs, list) and outputs else "").strip()
            if not uri:
                return {
                    "status": "failed",
                    "failureCode": "NO_VIDEO_OUTPUT",
                    "failureMessage": "Runway completed without a video file.",
                    "refundEligible": True,
                }
            return {"status": "ready", "outputUrl": _safe_https_url(uri, provider="runway")}

        failure_code = str(body.get("failureCode") or "")[:160]
        failure_message = " ".join(str(body.get("failure") or "Runway video generation failed.").split())[:500]
        billable_safety_failure = (
            failure_code.startswith("SAFETY.")
            or failure_code.startswith("INPUT_PREPROCESSING.SAFETY")
        )
        if billable_safety_failure:
            failure_message = "Runway could not generate that request under its safety rules."
        return {
            "status": "failed",
            "failureCode": failure_code or ("CANCELED" if status == "CANCELED" else "RUNWAY_FAILED"),
            "failureMessage": failure_message,
            # Runway currently documents input-safety failures as non-refundable
            # provider spend. Do not turn them into a free retry loop. Other
            # failures return the Ask Crump generation charge.
            "refundEligible": not billable_safety_failure,
        }

    async def download(self, uri: str, *, max_bytes: int) -> bytes:
        return await _bounded_provider_download(
            uri,
            provider="runway",
            max_bytes=max_bytes,
        )
