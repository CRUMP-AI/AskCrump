"""Canonical, content-free contract for the connected release ceremony."""

from __future__ import annotations

import hashlib
import json


CONNECTED_RELEASE_PREVIEW_GOOGLE_REDIRECT = (
    "https://www.askcrump.com/api/connected-apps/oauth/callback/google"
)
CONNECTED_RELEASE_PREVIEW_MICROSOFT_REDIRECT = (
    "https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft"
)

_CONNECTED_RELEASE_PREVIEW_CONTRACT = {
    "version": "askcrump-connected-release-preview-v1",
    "source_locks": {
        "preview": "required_true",
        "public_connected_apps": "required_true",
        "durable_multi_step": "required_true",
        "activation": "readiness_fail_closed_until_same_deployment_ceremony",
        "post_ceremony_redeploy": "forbidden",
    },
    "accounts": "operator_attested_dedicated_non_customer_only",
    "providers": {
        "google": {
            "callback": CONNECTED_RELEASE_PREVIEW_GOOGLE_REDIRECT,
            "account_kinds": ["personal"],
            "resources": ["mail", "calendar"],
            "checks": [
                "oauth_callback",
                "bounded_read",
                "preview_write",
                "mail_send_reply_retained_test_artifact",
                "calendar_free_busy",
                "reversible_cleanup",
                "revocation",
            ],
        },
        "microsoft": {
            "callback": CONNECTED_RELEASE_PREVIEW_MICROSOFT_REDIRECT,
            "resources": ["mail", "calendar"],
            "account_kinds": ["personal", "work_school"],
            "checks": [
                "oauth_callback",
                "bounded_read",
                "preview_write",
                "mail_send_reply_retained_test_artifact",
                "calendar_free_busy_work_school",
                "calendar_free_busy_personal_explicitly_unsupported",
                "reversible_cleanup",
                "local_connection_retirement",
                "local_credential_erasure",
            ],
        },
    },
    "gateway": {
        "authentication": "current_vercel_request_oidc",
        "model": "openai/gpt-oss-20b",
        "provider": "groq",
        "retention": "zero_data_retention_and_no_prompt_training",
        "cost_receipt": "claim_then_settle",
    },
    "durability": {
        "effect_intent": "database_before_provider_dispatch",
        "readiness": "zero_unsettled_reversible_effects",
        "retained_mail": "content_free_hashed_ids_and_operator_confirmation",
    },
    "receipt": "database_challenge_kms_hmac_then_live_runtime_readiness",
}

CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256 = hashlib.sha256(
    json.dumps(
        _CONNECTED_RELEASE_PREVIEW_CONTRACT,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


__all__ = [
    "CONNECTED_RELEASE_PREVIEW_CONTRACT_SHA256",
    "CONNECTED_RELEASE_PREVIEW_GOOGLE_REDIRECT",
    "CONNECTED_RELEASE_PREVIEW_MICROSOFT_REDIRECT",
]
