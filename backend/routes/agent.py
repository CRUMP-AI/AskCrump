"""Agent capability registry endpoints.

The client fetches the registry at session start and renders task,
approval, artifact, connection, and brief cards from it. This surface is
read-only: executing a capability belongs to the agent run engine, and
unknown capability ids fail closed with ``CAPABILITY_NOT_FOUND``.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..agent_registry import get_capability, public_catalog
from ..auth_service import authenticate_request
from ..runtime import db, settings

router = APIRouter(prefix='/api/agent', tags=['agent'])


@router.get('/capabilities')
async def list_capabilities(request: Request):
    await authenticate_request(
        request,
        db,
        settings,
        require_account=True,
        require_expected_owner_header=True,
    )
    return JSONResponse(
        content={'success': True, **public_catalog()},
        headers={'Cache-Control': 'private, no-store'},
    )


@router.get('/capabilities/{capability_id}')
async def describe_capability(capability_id: str, request: Request):
    await authenticate_request(
        request,
        db,
        settings,
        require_account=True,
        require_expected_owner_header=True,
    )
    item = get_capability(capability_id)
    if item is None:
        return JSONResponse(
            status_code=404,
            content={
                'success': False,
                'error': 'That capability is not available.',
                'code': 'CAPABILITY_NOT_FOUND',
            },
            headers={'Cache-Control': 'private, no-store'},
        )
    return JSONResponse(
        content={'success': True, 'capability': item.public_dict()},
        headers={'Cache-Control': 'private, no-store'},
    )
