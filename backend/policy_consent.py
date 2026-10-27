"""Exact, auditable policy-bundle acceptance contract.

The committed public manifest and the PostgreSQL migration mirror these
constants. ``scripts/verify-policy-bundle.mjs`` fails CI if any covered legal
copy, mirror, or migration seed drifts without a deliberate bundle update.
"""

from __future__ import annotations

from typing import Any, Literal

from .db import SupabaseDB


CURRENT_POLICY_BUNDLE_ID = "ask-crump-legal-2026-08-01-a44e8c36"
CURRENT_POLICY_BUNDLE_HASH = (
    "a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a"
)

CURRENT_POLICY_COMPONENTS = {
    "terms": {
        "id": "ask-crump-terms-v1",
        "sha256": "5ef56db9335386895dd9bfb90589e15d766bf9b7c4401defe4ec38568d98f258",
    },
    "privacy": {
        "id": "ask-crump-privacy-v1",
        "sha256": "4191cbfbeb311232797c2645d7d2e4616dea6ca3cd7161f70b2caba0e88a8ddf",
    },
    "ageAttestation": {
        "id": "ask-crump-age-17-v1",
        "sha256": "d3d8e283bf73ceb97867d09d50497635fc875af042d3d4f0ea5d1122bd235b99",
    },
    "providerDisclosure": {
        "id": "ask-crump-ai-provider-disclosure-v1",
        "sha256": "b145250398b66900d5f00687158cba029b0b5407c90d3a73ab8ca9fc4e809d73",
    },
}

PolicyAcceptanceSource = Literal["registration", "guest_gate", "account_gate"]
PolicyClientPlatform = Literal["unknown"]

# Web and native clients use the same public endpoints. No request header,
# user-agent, installation identifier, or payload field proves which binary
# sent a request, so the transition records the bounded honest provenance.
UNTRUSTED_CLIENT_PLATFORM: PolicyClientPlatform = "unknown"


def _single_row(result: Any) -> dict[str, Any]:
    if isinstance(result, list):
        return result[0] if result and isinstance(result[0], dict) else {}
    return result if isinstance(result, dict) else {}


async def record_current_policy_acceptance(
    db: SupabaseDB,
    *,
    user_id: str,
    source: PolicyAcceptanceSource,
    platform: PolicyClientPlatform,
    age_17_plus_attested: bool,
    terms_accepted: bool,
    privacy_notice_acknowledged: bool,
    ai_provider_transmission_authorized: bool,
) -> dict[str, Any]:
    """Append the current receipt and mirror its server timestamp atomically."""
    row = _single_row(await db.rpc(
        "record_policy_acceptance_v1",
        {
            "p_user_id": user_id,
            "p_bundle_id": CURRENT_POLICY_BUNDLE_ID,
            "p_acceptance_source": source,
            "p_client_platform": platform,
            "p_age_17_plus_attested": age_17_plus_attested,
            "p_terms_accepted": terms_accepted,
            "p_privacy_notice_acknowledged": privacy_notice_acknowledged,
            "p_ai_provider_transmission_authorized": ai_provider_transmission_authorized,
        },
    ))
    if (
        not row.get("receipt_id")
        or not row.get("accepted_at")
        or row.get("bundle_id") != CURRENT_POLICY_BUNDLE_ID
        or row.get("bundle_hash") != CURRENT_POLICY_BUNDLE_HASH
    ):
        raise RuntimeError("Policy acceptance did not return an exact durable receipt.")
    return row


async def read_current_policy_acceptance(
    db: SupabaseDB,
    *,
    user_id: str,
) -> dict[str, Any] | None:
    """Return only a receipt bound to the exact current immutable manifest."""
    row = _single_row(await db.rpc(
        "read_current_policy_acceptance_v1",
        {"p_user_id": user_id},
        retry_transient=True,
    ))
    if not row:
        return None
    if (
        row.get("bundle_id") != CURRENT_POLICY_BUNDLE_ID
        or row.get("bundle_hash") != CURRENT_POLICY_BUNDLE_HASH
    ):
        return None
    return row
