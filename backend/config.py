from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


def _csv(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip().rstrip('/') for item in value.split(',') if item.strip())


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _transactional_from_email(environment: str, configured: str | None) -> str:
    # Keep production transactional mail off Resend's test-only sender.
    default = 'Ask Crump <noreply@askcrump.com>'
    value = str(configured or '').strip() or default
    if environment == 'production' and '@resend.dev' in value.lower():
        return default
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_url: str
    environment: str
    supabase_url: str
    supabase_service_key: str
    anthropic_api_key: str | None
    anthropic_model: str
    openai_api_key: str | None
    openai_image_model: str
    openai_vision_model: str
    gemini_api_key: str | None
    gemini_video_model: str
    gemini_video_extend_model: str
    runway_api_secret: str | None
    runway_video_model: str
    runway_api_version: str
    storage_bucket: str
    max_upload_bytes: int
    brave_api_key: str | None
    openweather_api_key: str | None
    web_search_enabled: bool
    image_generation_enabled: bool
    video_generation_enabled: bool
    manuscript_generation_enabled: bool
    max_active_video_jobs_per_user: int
    max_generated_video_bytes: int
    video_daily_provider_budget_cents: int
    video_user_daily_provider_budget_cents: int
    runway_monthly_provider_budget_cents: int
    resend_api_key: str | None
    from_email: str
    support_email: str
    stripe_secret_key: str | None
    stripe_webhook_secret: str | None
    stripe_professional_price_id: str | None
    stripe_enterprise_price_id: str | None
    revenuecat_webhook_auth: str | None
    revenuecat_secret_api_key: str | None
    cron_secret: str | None
    fcm_project_id: str | None
    google_service_account_json: str | None
    apns_key_id: str | None
    apns_team_id: str | None
    apns_bundle_id: str | None
    apns_private_key: str | None
    apns_environment: str
    check_in_batch_size: int
    allowed_origins: tuple[str, ...]
    session_cookie_name: str
    session_days: int
    cookie_domain: str | None
    cookie_secure: bool
    max_request_bytes: int
    max_history_messages: int
    max_history_chars: int
    free_daily_messages: int
    professional_daily_messages: int
    enterprise_daily_messages: int

    @property
    def is_production(self) -> bool:
        return self.environment == 'production'

    def validate_required(self) -> None:
        missing = []
        if not self.supabase_url:
            missing.append('SUPABASE_URL')
        if not self.supabase_service_key:
            missing.append('SUPABASE_SERVICE_KEY')
        if self.is_production and not self.anthropic_api_key:
            missing.append('ANTHROPIC_API_KEY')
        if self.is_production and not self.resend_api_key:
            missing.append('RESEND_API_KEY')
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        if self.is_production and not self.app_url.startswith('https://'):
            raise RuntimeError('APP_URL must use HTTPS in production.')
        if self.is_production and not self.cookie_secure:
            raise RuntimeError('COOKIE_SECURE must be true in production.')
        if '*' in self.allowed_origins:
            raise RuntimeError('ALLOWED_ORIGINS cannot contain * when credentials are enabled.')
        if not 1 <= self.session_days <= 3650:
            raise RuntimeError('SESSION_DAYS must be between 1 and 3650.')
        if self.max_request_bytes < 1024:
            raise RuntimeError('MAX_REQUEST_BYTES is too small.')
        if self.max_upload_bytes < 1024 * 1024 or self.max_upload_bytes > 100 * 1024 * 1024:
            raise RuntimeError('MAX_UPLOAD_BYTES must be between 1 MB and 100 MB.')
        if self.max_history_messages < 1 or self.max_history_chars < 1000:
            raise RuntimeError('History limits must be positive.')
        if min(self.free_daily_messages, self.professional_daily_messages, self.enterprise_daily_messages) < 0:
            raise RuntimeError('Daily message limits cannot be negative.')
        if self.apns_environment not in {'production', 'sandbox'}:
            raise RuntimeError('APNS_ENVIRONMENT must be production or sandbox.')
        if not 1 <= self.check_in_batch_size <= 100:
            raise RuntimeError('CHECK_IN_BATCH_SIZE must be between 1 and 100.')
        if not 1 <= self.max_active_video_jobs_per_user <= 3:
            raise RuntimeError('MAX_ACTIVE_VIDEO_JOBS_PER_USER must be between 1 and 3.')
        if not 5 * 1024 * 1024 <= self.max_generated_video_bytes <= 100 * 1024 * 1024:
            raise RuntimeError('MAX_GENERATED_VIDEO_BYTES must be between 5 MB and 100 MB.')
        if min(
            self.video_daily_provider_budget_cents,
            self.video_user_daily_provider_budget_cents,
            self.runway_monthly_provider_budget_cents,
        ) < 0:
            raise RuntimeError('Video provider budget limits cannot be negative.')


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    environment = os.getenv('APP_ENV', os.getenv('VERCEL_ENV', 'development')).lower()
    app_url = os.getenv('APP_URL', 'http://localhost:3000').rstrip('/')
    production_origins = (
        app_url,
        'https://askcrump.com',
        'https://www.askcrump.com',
        'capacitor://localhost',
        'https://localhost',
    )
    development_origins = production_origins + ('http://localhost', 'http://localhost:3000')
    defaults = production_origins if environment == 'production' else development_origins

    settings = Settings(
        app_name=os.getenv('APP_NAME', 'Ask Crump'),
        app_url=app_url,
        environment=environment,
        supabase_url=os.getenv('SUPABASE_URL', '').rstrip('/'),
        supabase_service_key=os.getenv('SUPABASE_SERVICE_KEY', ''),
        anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
        anthropic_model=os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-5'),
        openai_api_key=os.getenv('OPENAI_API_KEY'),
        openai_image_model=os.getenv('OPENAI_IMAGE_MODEL', 'gpt-image-2'),
        openai_vision_model=os.getenv('OPENAI_VISION_MODEL', 'gpt-5.6-sol'),
        gemini_api_key=os.getenv('GEMINI_API_KEY'),
        gemini_video_model=os.getenv('GEMINI_VIDEO_MODEL', 'veo-3.1-lite-generate-preview'),
        gemini_video_extend_model=os.getenv('GEMINI_VIDEO_EXTEND_MODEL', 'veo-3.1-fast-generate-preview'),
        runway_api_secret=os.getenv('RUNWAYML_API_SECRET'),
        runway_video_model=os.getenv('RUNWAY_VIDEO_MODEL', 'gen4.5'),
        runway_api_version=os.getenv('RUNWAY_API_VERSION', '2024-11-06'),
        storage_bucket=os.getenv('CRUMP_STORAGE_BUCKET', 'crump-files'),
        max_upload_bytes=int(os.getenv('MAX_UPLOAD_BYTES', str(50 * 1024 * 1024))),
        brave_api_key=os.getenv('BRAVE_API_KEY'),
        openweather_api_key=os.getenv('OPENWEATHER_API_KEY'),
        web_search_enabled=_bool(os.getenv('CRUMP_ENABLE_WEB_SEARCH'), True),
        image_generation_enabled=_bool(os.getenv('CRUMP_ENABLE_IMAGE_GENERATION'), True),
        # A configured Gemini key is sufficient by default. Operators can still
        # explicitly set this false as an emergency cost/safety switch.
        video_generation_enabled=_bool(os.getenv('CRUMP_ENABLE_VIDEO_GENERATION'), True),
        manuscript_generation_enabled=_bool(os.getenv('CRUMP_ENABLE_MANUSCRIPTS'), True),
        max_active_video_jobs_per_user=int(os.getenv('MAX_ACTIVE_VIDEO_JOBS_PER_USER', '1')),
        max_generated_video_bytes=int(os.getenv('MAX_GENERATED_VIDEO_BYTES', str(45 * 1024 * 1024))),
        # Early-launch circuit breakers. These are provider-cost estimates, not
        # user-facing credit limits, and can be raised deliberately in Vercel.
        video_daily_provider_budget_cents=int(os.getenv('VIDEO_DAILY_PROVIDER_BUDGET_CENTS', '10000')),
        video_user_daily_provider_budget_cents=int(os.getenv('VIDEO_USER_DAILY_PROVIDER_BUDGET_CENTS', '2000')),
        runway_monthly_provider_budget_cents=int(os.getenv('RUNWAY_MONTHLY_PROVIDER_BUDGET_CENTS', '50000')),
        resend_api_key=os.getenv('RESEND_API_KEY'),
        from_email=_transactional_from_email(environment, os.getenv('FROM_EMAIL')),
        support_email=os.getenv('SUPPORT_EMAIL', 'support@askcrump.com'),
        stripe_secret_key=os.getenv('STRIPE_SECRET_KEY'),
        stripe_webhook_secret=os.getenv('STRIPE_WEBHOOK_SECRET'),
        stripe_professional_price_id=os.getenv('STRIPE_PROFESSIONAL_PRICE_ID'),
        stripe_enterprise_price_id=os.getenv('STRIPE_ENTERPRISE_PRICE_ID'),
        revenuecat_webhook_auth=os.getenv('REVENUECAT_WEBHOOK_AUTH'),
        revenuecat_secret_api_key=os.getenv('REVENUECAT_SECRET_API_KEY'),
        cron_secret=os.getenv('CRON_SECRET'),
        fcm_project_id=os.getenv('FCM_PROJECT_ID'),
        google_service_account_json=os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'),
        apns_key_id=os.getenv('APNS_KEY_ID'),
        apns_team_id=os.getenv('APNS_TEAM_ID'),
        apns_bundle_id=os.getenv('APNS_BUNDLE_ID', 'com.clevercrump.askcrump'),
        apns_private_key=os.getenv('APNS_PRIVATE_KEY'),
        apns_environment=os.getenv('APNS_ENVIRONMENT', 'production' if environment == 'production' else 'sandbox').lower(),
        check_in_batch_size=int(os.getenv('CHECK_IN_BATCH_SIZE', '10')),
        allowed_origins=_csv(os.getenv('ALLOWED_ORIGINS'), defaults),
        session_cookie_name=os.getenv('SESSION_COOKIE_NAME', 'crump_session'),
        session_days=int(os.getenv('SESSION_DAYS', '365')),
        cookie_domain=os.getenv('COOKIE_DOMAIN') or None,
        cookie_secure=_bool(os.getenv('COOKIE_SECURE'), environment == 'production'),
        max_request_bytes=int(os.getenv('MAX_REQUEST_BYTES', str(5 * 1024 * 1024))),
        max_history_messages=int(os.getenv('MAX_HISTORY_MESSAGES', '120')),
        max_history_chars=int(os.getenv('MAX_HISTORY_CHARS', '450000')),
        free_daily_messages=int(os.getenv('FREE_DAILY_MESSAGES', '25')),
        professional_daily_messages=int(os.getenv('PROFESSIONAL_DAILY_MESSAGES', '500')),
        enterprise_daily_messages=int(os.getenv('ENTERPRISE_DAILY_MESSAGES', '5000')),
    )
    settings.validate_required()
    return settings
