from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
import json

import httpx

from .config import Settings


@dataclass(slots=True)
class DatabaseError(RuntimeError):
    message: str
    status_code: int = 500
    details: Any = None

    def __str__(self) -> str:
        return self.message


class SupabaseDB:
    """Small async PostgREST client using the Supabase service-role key.

    Keeping database access explicit avoids pulling the full Node/Supabase stack into
    the Python function and makes every query easy to audit and test.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

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
    ) -> Any:
        headers = self.headers
        if prefer:
            headers['Prefer'] = prefer
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=timeout)
        try:
            response = await client.request(
                method,
                f"{self.base_url}/{table}",
                params=params,
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise DatabaseError('Database connection failed', 503, str(exc)) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code >= 400:
            try:
                details = response.json()
            except ValueError:
                details = response.text[:1000]
            raise DatabaseError('Database operation failed', response.status_code, details)

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

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
    ) -> Any:
        return await self.request(
            'PATCH', table, params=filters, payload=payload, prefer='return=representation'
        )

    async def delete(self, table: str, *, filters: dict[str, Any]) -> Any:
        return await self.request(
            'DELETE', table, params=filters, prefer='return=representation'
        )

    async def rpc(self, function_name: str, payload: dict[str, Any]) -> Any:
        return await self.request('POST', f'rpc/{function_name}', payload=payload)


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
