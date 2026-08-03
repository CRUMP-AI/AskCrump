"""Vercel ASGI entry point for Ask Crump's API routes."""

from backend.application import create_app

app = create_app()
