"""Process-scoped service instances used by the API routes.

Vercel runs the FastAPI application as a single Python function. Keeping these
clients at module scope allows connection reuse across warm invocations while
preserving a small, explicit dependency surface for tests.
"""

from __future__ import annotations

from .ai_service import AIService
from .config import get_settings
from .db import SupabaseDB
from .email_service import EmailService
from .push_service import PushService

settings = get_settings()
db = SupabaseDB(settings)
ai = AIService(settings)
email_service = EmailService(settings)
push_service = PushService(settings)
