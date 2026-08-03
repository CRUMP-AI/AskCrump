"""Vercel ASGI entry point for Ask Crump."""

from backend.application import create_app

app = create_app()
