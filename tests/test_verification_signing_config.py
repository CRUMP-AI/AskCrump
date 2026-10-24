from dataclasses import replace

import pytest

from backend.config import PRODUCTION_SUPABASE_ORIGIN, _verification_signing_keys
from backend.runtime import settings


CURRENT_SECRET = "c" * 43
PREVIOUS_SECRET = "p" * 64


def test_verification_signing_key_ring_preserves_rotation_order():
    assert _verification_signing_keys(
        f"current:{CURRENT_SECRET},previous:{PREVIOUS_SECRET}"
    ) == (
        ("current", CURRENT_SECRET),
        ("previous", PREVIOUS_SECRET),
    )


@pytest.mark.parametrize(
    "value",
    [
        "missing-separator",
        f"bad key:{CURRENT_SECRET}",
        "current:short",
        f"current:{CURRENT_SECRET},current:{PREVIOUS_SECRET}",
        f"current:{'!' * 43}",
    ],
)
def test_verification_signing_key_ring_rejects_ambiguous_or_weak_values(value):
    with pytest.raises(RuntimeError, match="VERIFICATION_LINK_SIGNING_KEYS is invalid"):
        _verification_signing_keys(value)


@pytest.mark.parametrize("environment", ["production", "preview"])
def test_hosted_environment_requires_verification_signing_key_ring(environment):
    hosted_settings = replace(
        settings,
        environment=environment,
        app_url="https://www.askcrump.com",
        cookie_secure=True,
        supabase_url=PRODUCTION_SUPABASE_ORIGIN,
        supabase_service_key="production-service-key",
        verification_link_signing_keys=(),
        anthropic_api_key="production-anthropic-key",
        ai_gateway_enabled=False,
        resend_api_key="production-resend-key",
    )

    with pytest.raises(RuntimeError, match="VERIFICATION_LINK_SIGNING_KEYS"):
        hosted_settings.validate_required()
