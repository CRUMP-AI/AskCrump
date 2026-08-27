"""Process-scoped service instances used by the API routes."""
from __future__ import annotations

from .ai_service import AIService
from .artifact_service import ArtifactService
from .code_runner import CrumpCodeRunner
from .code_service import CodeTaskService
from .config import get_settings
from .db import SupabaseDB
from .email_service import EmailService
from .feature_service import FeatureService
from .file_service import FileService
from .intelligence_service import IntelligenceService
from .manuscript_service import ManuscriptService
from .media_service import MediaService
from .project_service import ProjectService
from .video_service import VideoService
from .voice_service import ElevenLabsVoiceService
from .push_service import PushService

settings = get_settings()
db = SupabaseDB(settings)
ai = AIService(settings)
files = FileService(settings, db)
features = FeatureService(db)
projects = ProjectService(db)
code_tasks = CodeTaskService(db, projects)
code_runner = CrumpCodeRunner(settings, code_tasks)
voice = ElevenLabsVoiceService(settings)
media = MediaService(settings, files)
video = VideoService(settings, db, files)
manuscripts = ManuscriptService(db, ai, projects, features, files)
artifacts = ArtifactService(files)
intelligence = IntelligenceService(db=db, ai=ai, settings=settings)
email_service = EmailService(settings)
push_service = PushService(settings)
