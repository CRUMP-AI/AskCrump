"""Operational health endpoint."""

from fastapi import APIRouter

from ..runtime import settings
from ..security import iso_now
from ..version import __version__

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health():
    return {
        "success": True,
        "service": settings.app_name,
        "version": __version__,
        "time": iso_now(),
    }
