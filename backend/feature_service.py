"""Cost-aware feature entitlements for Ask Crump 5.4.

This layer sits beside the existing message allowance. Expensive provider calls use
feature-specific included quotas and Crump Credit overflow so a single user cannot
silently create an unbounded image/video/search bill.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .db import SupabaseDB
from .usage_service import credit_status, has_internal_access, refund_usage, tier_name


TIER_RANK = {"free": 0, "professional": 1, "enterprise": 2}


@dataclass(frozen=True, slots=True)
class FeaturePolicy:
    code: str
    label: str
    minimum_tier: str
    credit_cost: int
    included_daily: dict[str, int]
    provider_env: str | None = None


POLICIES: dict[str, FeaturePolicy] = {
    "research": FeaturePolicy(
        "research",
        "Live research & current data",
        "free",
        1,
        {"free": 1, "professional": 20, "enterprise": 50},
        "BRAVE_API_KEY",
    ),
    "image": FeaturePolicy(
        "image",
        "Image generation",
        "professional",
        6,
        {"free": 0, "professional": 1, "enterprise": 2},
        "OPENAI_API_KEY",
    ),
    "image_edit": FeaturePolicy(
        "image_edit",
        "Image editing",
        "professional",
        10,
        {"free": 0, "professional": 0, "enterprise": 0},
        "OPENAI_API_KEY",
    ),
    "video": FeaturePolicy(
        "video",
        "Video generation",
        "professional",
        60,
        {"free": 0, "professional": 0, "enterprise": 0},
        "GEMINI_API_KEY",
    ),
    "video_hd": FeaturePolicy(
        "video_hd",
        "HD video generation",
        "professional",
        90,
        {"free": 0, "professional": 0, "enterprise": 0},
        "GEMINI_API_KEY",
    ),
    "manuscript_draft": FeaturePolicy(
        "manuscript_draft",
        "Long-form manuscript drafting",
        "free",
        8,
        {"free": 0, "professional": 2, "enterprise": 4},
        "ANTHROPIC_API_KEY",
    ),
    "manuscript_blueprint": FeaturePolicy(
        "manuscript_blueprint",
        "Manuscript planning",
        "free",
        4,
        {"free": 0, "professional": 1, "enterprise": 2},
        "ANTHROPIC_API_KEY",
    ),
    "kdp_export": FeaturePolicy(
        "kdp_export",
        "KDP manuscript export",
        "free",
        0,
        {"free": -1, "professional": -1, "enterprise": -1},
        None,
    ),
}

PROJECT_LIMITS = {"free": 2, "professional": 25, "enterprise": 200}


@dataclass(slots=True)
class FeatureAccessError(RuntimeError):
    message: str
    code: str = "FEATURE_ACCESS_DENIED"
    status_code: int = 403
    required_tier: str | None = None
    credit_cost: int = 0
    credit_balance: int = 0

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


class FeatureService:
    def __init__(self, db: SupabaseDB) -> None:
        self.db = db

    @staticmethod
    def policy(code: str) -> FeaturePolicy:
        normalized = str(code or "").strip().lower()
        policy = POLICIES.get(normalized)
        if not policy:
            raise FeatureAccessError("Unknown feature.", "UNKNOWN_FEATURE", 400)
        return policy

    @staticmethod
    def project_limit(user: dict[str, Any]) -> int:
        if has_internal_access(user):
            return -1
        return PROJECT_LIMITS[tier_name(user)]

    @staticmethod
    def _tier_allowed(tier: str, minimum: str) -> bool:
        return TIER_RANK.get(tier, 0) >= TIER_RANK.get(minimum, 0)

    async def status(self, user: dict[str, Any]) -> dict[str, Any]:
        tier = tier_name(user)
        internal_access = has_internal_access(user)
        credits = await credit_status(self.db, user["id"])
        return {
            "tier": tier,
            "internalAccess": internal_access,
            "accessSource": "internal" if internal_access else "billing",
            "creditBalance": credits["balance"],
            "projectLimit": -1 if internal_access else PROJECT_LIMITS[tier],
            "features": {
                code: {
                    "label": policy.label,
                    "minimumTier": policy.minimum_tier,
                    "entitled": internal_access or self._tier_allowed(tier, policy.minimum_tier),
                    "includedDaily": -1 if internal_access else policy.included_daily[tier],
                    "overflowCredits": 0 if internal_access else policy.credit_cost,
                    "standardOverflowCredits": policy.credit_cost,
                    "accessSource": "internal" if internal_access else "billing",
                }
                for code, policy in POLICIES.items()
            },
        }

    async def require_tier(self, user: dict[str, Any], code: str) -> FeaturePolicy:
        policy = self.policy(code)
        if has_internal_access(user):
            return policy
        tier = tier_name(user)
        if not self._tier_allowed(tier, policy.minimum_tier):
            credits = await credit_status(self.db, user["id"])
            raise FeatureAccessError(
                f"{policy.label} requires a {policy.minimum_tier.title()} plan.",
                "SUBSCRIPTION_REQUIRED",
                403,
                policy.minimum_tier,
                policy.credit_cost,
                credits["balance"],
            )
        return policy

    async def consume(
        self,
        user: dict[str, Any],
        code: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = await self.require_tier(user, code)
        if has_internal_access(user):
            credits = await credit_status(self.db, user["id"])
            return {
                "feature": code,
                "paymentSource": "internal",
                "eventId": None,
                "creditBalance": credits["balance"],
                "creditsSpent": 0,
                "internalAccess": True,
            }
        tier = tier_name(user)
        included = policy.included_daily[tier]
        details = {"feature": code, **(metadata or {})}

        if included < 0:
            credits = await credit_status(self.db, user["id"])
            return {
                "feature": code,
                "paymentSource": "subscription",
                "eventId": None,
                "creditBalance": credits["balance"],
                "creditsSpent": 0,
            }

        included_result = await self.db.rpc(
            "consume_usage_event",
            {
                "p_user_id": user["id"],
                "p_event_type": f"feature:{code}",
                "p_limit": included,
                "p_metadata": details,
            },
        )
        row = (
            included_result[0]
            if isinstance(included_result, list) and included_result
            else (included_result or {})
        )
        if row.get("allowed"):
            credits = await credit_status(self.db, user["id"])
            return {
                "feature": code,
                "paymentSource": "included",
                "eventId": row.get("event_id"),
                "creditBalance": credits["balance"],
                "creditsSpent": 0,
            }

        if policy.credit_cost <= 0:
            raise FeatureAccessError(
                f"Your included {policy.label.lower()} allowance is exhausted.",
                "FEATURE_LIMIT_REACHED",
                403,
                policy.minimum_tier,
            )

        credit_result = await self.db.rpc(
            "spend_credits",
            {
                "p_user_id": user["id"],
                "p_amount": policy.credit_cost,
                "p_reason": f"feature_{code}",
                "p_metadata": details,
            },
        )
        credit_row = (
            credit_result[0]
            if isinstance(credit_result, list) and credit_result
            else (credit_result or {})
        )
        balance = max(0, int(credit_row.get("balance") or 0))
        if not credit_row.get("allowed"):
            raise FeatureAccessError(
                f"{policy.label} needs {policy.credit_cost} Crump Credits after included usage.",
                "CREDITS_REQUIRED",
                402,
                policy.minimum_tier,
                policy.credit_cost,
                balance,
            )

        ledger_id = credit_row.get("ledger_id")
        return {
            "feature": code,
            "paymentSource": "credits",
            "eventId": f"credit:{ledger_id}" if ledger_id else None,
            "creditBalance": balance,
            "creditsSpent": policy.credit_cost,
        }

    async def refund(self, user_id: str, receipt: dict[str, Any] | None) -> None:
        if not receipt:
            return
        await refund_usage(self.db, user_id, receipt.get("eventId"))
