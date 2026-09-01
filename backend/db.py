from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
import logging
from typing import Any, Iterable

import httpx

from .config import Settings

logger = logging.getLogger("askcrump.database")

_RETRYABLE_READ_METHODS = frozenset({"GET", "HEAD"})
_RETRYABLE_READ_STATUSES = frozenset({408, 503, 504, 520})
_READ_RETRY_DELAYS_SECONDS = (0.25, 0.75, 1.5)


@dataclass(slots=True)
class DatabaseError(RuntimeError):
    message: str
    status_code: int = 500
    details: Any = None
    retryable: bool = False
    retry_after: int = 0
    attempts: int = 1

    def __str__(self) -> str:
        return self.message


class SupabaseDB:
    """Small async PostgREST client using the Supabase service-role key.

    Keeping database access explicit avoids pulling the full Node/Supabase stack into
    the Python function and makes every query easy to audit and test.
    """

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self._client = client
        self._sleep = sleep

    @property
    def base_url(self) -> str:
        return f"{self.settings.supabase_url}/rest/v1"

    @property
    def headers(self) -> dict[str, str]:
        key = self.settings.supabase_service_key
        return {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    async def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any = None,
        prefer: str | None = None,
        timeout: float = 20.0,
        retry_transient: bool = False,
    ) -> Any:
        method = method.upper()
        retryable_request = method in _RETRYABLE_READ_METHODS or retry_transient
        headers = self.headers
        if prefer:
            headers['Prefer'] = prefer
        owns_client = self._client is None
        request_timeout = httpx.Timeout(
            timeout,
            connect=min(5.0, timeout),
            pool=min(5.0, timeout),
        )
        client = self._client or httpx.AsyncClient(timeout=request_timeout)
        try:
            for attempt in range(len(_READ_RETRY_DELAYS_SECONDS) + 1):
                request_headers = dict(headers)
                if attempt:
                    request_headers['X-Retry-Count'] = str(attempt)
                try:
                    response = await client.request(
                        method,
                        f"{self.base_url}/{table}",
                        params=params,
                        json=payload,
                        headers=request_headers,
                        timeout=request_timeout,
                    )
                except httpx.HTTPError as exc:
                    if retryable_request and attempt < len(_READ_RETRY_DELAYS_SECONDS):
                        delay = _READ_RETRY_DELAYS_SECONDS[attempt]
                        logger.warning(
                            "Database read transport retry attempt=%s delay_seconds=%.2f error_type=%s",
                            attempt + 1,
                            delay,
                            type(exc).__name__,
                        )
                        await self._sleep(delay)
                        continue
                    raise DatabaseError(
                        'Database connection failed',
                        503,
                        {'error_type': type(exc).__name__},
                        retryable=retryable_request,
                        retry_after=2 if retryable_request else 0,
                        attempts=attempt + 1,
                    ) from exc

                transient_status = response.status_code in _RETRYABLE_READ_STATUSES
                if (
                    retryable_request
                    and transient_status
                    and attempt < len(_READ_RETRY_DELAYS_SECONDS)
                ):
                    delay = _READ_RETRY_DELAYS_SECONDS[attempt]
                    logger.warning(
                        "Database read status retry status=%s attempt=%s delay_seconds=%.2f",
                        response.status_code,
                        attempt + 1,
                        delay,
                    )
                    await self._sleep(delay)
                    continue

                if response.status_code >= 400:
                    try:
                        details = response.json()
                    except ValueError:
                        details = response.text[:1000]
                    raise DatabaseError(
                        'Database operation failed',
                        response.status_code,
                        details,
                        retryable=retryable_request and transient_status,
                        retry_after=2 if retryable_request and transient_status else 0,
                        attempts=attempt + 1,
                    )

                if not response.content:
                    return None
                try:
                    return response.json()
                except ValueError:
                    return response.text
        finally:
            if owns_client:
                await client.aclose()

        raise RuntimeError('Database request retry loop exited unexpectedly.')

    async def select(
        self,
        table: str,
        *,
        columns: str = '*',
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {'select': columns}
        if filters:
            params.update(filters)
        if order:
            params['order'] = order
        if limit is not None:
            params['limit'] = str(limit)
        data = await self.request('GET', table, params=params)
        return data or []

    async def select_one(
        self,
        table: str,
        *,
        columns: str = '*',
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = await self.select(table, columns=columns, filters=filters, limit=1)
        return rows[0] if rows else None

    async def insert(self, table: str, payload: dict[str, Any] | list[dict[str, Any]]) -> Any:
        return await self.request(
            'POST', table, payload=payload, prefer='return=representation'
        )

    async def upsert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> Any:
        return await self.request(
            'POST',
            table,
            params={'on_conflict': on_conflict},
            payload=payload,
            prefer='resolution=merge-duplicates,return=representation',
        )

    async def update(
        self,
        table: str,
        payload: dict[str, Any],
        *,
        filters: dict[str, Any],
        retry_transient: bool = False,
    ) -> Any:
        return await self.request(
            'PATCH',
            table,
            params=filters,
            payload=payload,
            prefer='return=representation',
            retry_transient=retry_transient,
        )

    async def delete(self, table: str, *, filters: dict[str, Any]) -> Any:
        return await self.request(
            'DELETE', table, params=filters, prefer='return=representation'
        )

    async def rpc(
        self,
        function_name: str,
        payload: dict[str, Any],
        *,
        retry_transient: bool = False,
    ) -> Any:
        return await self.request(
            'POST',
            f'rpc/{function_name}',
            payload=payload,
            retry_transient=retry_transient,
        )


def eq(value: Any) -> str:
    if value is None:
        return 'is.null'
    if isinstance(value, bool):
        return f"eq.{str(value).lower()}"
    return f'eq.{value}'


def gt(value: Any) -> str:
    return f'gt.{value}'


def gte(value: Any) -> str:
    return f'gte.{value}'


def lte(value: Any) -> str:
    return f'lte.{value}'


def lt(value: Any) -> str:
    return f'lt.{value}'


def is_null() -> str:
    return 'is.null'


def in_(values: Iterable[Any]) -> str:
    encoded = ','.join(json.dumps(value, separators=(',', ':')) for value in values)
    return f'in.({encoded})'
