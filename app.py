"""Vercel and ASGI entry point."""

from backend.application import create_app

app = create_app()
