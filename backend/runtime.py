"""Process-scoped service instances used by the API routes."""
from __future__ import annotations

from .ai_service import AIService
from .artifact_service import ArtifactService
from .config import get_settings
from .db import SupabaseDB
from .email_service import EmailService
from .file_service import FileService
from .intelligence_service import IntelligenceService
from .media_service import MediaService
from .push_service import PushService

settings = get_settings()
db = SupabaseDB(settings)
ai = AIService(settings)
files = FileService(settings, db)
media = MediaService(settings, files)
artifacts = ArtifactService(files)
intelligence = IntelligenceService(db=db, ai=ai, settings=settings)
email_service = EmailService(settings)
push_service = PushService(settings)
