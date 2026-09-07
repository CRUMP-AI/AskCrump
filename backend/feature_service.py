"""Cost-aware feature entitlements for Ask Crump 5.4.

This layer sits beside the existing message allowance. Expensive provider calls use
feature-specific included quotas and Crump Credit overflow so a single user cannot
silently create an unbounded image/video/search bill.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import uuid4

from .db import SupabaseDB, eq, gte
from .usage_service import (
    credit_status,
    day_start_iso,
    has_internal_access,
    refund_usage,
    tier_name,
)


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
    "think_longer": FeaturePolicy(
        "think_longer",
        "Think longer",
        "professional",
        0,
        {"free": 0, "professional": -1, "enterprise": -1},
        "ANTHROPIC_API_KEY",
    ),
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
    "visual_analysis": FeaturePolicy(
        "visual_analysis",
        "Image and PDF understanding",
        "professional",
        2,
        {"free": 0, "professional": 20, "enterprise": 100},
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
    "video_extendable": FeaturePolicy(
        "video_extendable",
        "Extendable video generation",
        "professional",
        80,
        {"free": 0, "professional": 0, "enterprise": 0},
        "GEMINI_API_KEY",
    ),
    "video_continue": FeaturePolicy(
        "video_continue",
        "Continue video",
        "professional",
        80,
        {"free": 0, "professional": 0, "enterprise": 0},
        "GEMINI_API_KEY",
    ),
    "video_cinematic_5": FeaturePolicy(
        "video_cinematic_5",
        "Cinematic video generation",
        "professional",
        60,
        {"free": 0, "professional": 0, "enterprise": 0},
        "RUNWAYML_API_SECRET",
    ),
    "video_cinematic_10": FeaturePolicy(
        "video_cinematic_10",
        "10-second cinematic video generation",
        "enterprise",
        120,
        {"free": 0, "professional": 0, "enterprise": 0},
        "RUNWAYML_API_SECRET",
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
    "code_workspace": FeaturePolicy(
        "code_workspace",
        "Crump Code",
        "professional",
        12,
        {"free": 0, "professional": 3, "enterprise": 10},
        "ANTHROPIC_API_KEY",
    ),
    "premium_voice": FeaturePolicy(
        "premium_voice",
        "Crump Voice",
        "professional",
        2,
        {"free": 0, "professional": 10, "enterprise": 30},
        "ELEVENLABS_API_KEY",
    ),
}

PROJECT_LIMITS = {"free": 2, "professional": 25, "enterprise": 200}
MESSAGE_CODE = "messages"
QUOTE_TTL_SECONDS = 5 * 60


@dataclass(slots=True)
class FeatureAccessError(RuntimeError):
    message: str
    code: str = "FEATURE_ACCESS_DENIED"
    status_code: int = 403
    required_tier: str | None = None
    credit_cost: int = 0
    credit_balance: int = 0
    quote: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


@dataclass(frozen=True, slots=True)
class CreditAuthorization:
    user_id: str
    action_key: str
    max_by_code: dict[str, int]
    quantities: dict[str, int]
    confirmed_credits: int
    durable: bool = False


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


class FeatureService:
    def __init__(self, db: SupabaseDB, signing_secret: str | None = None) -> None:
        self.db = db
        configured_secret = str(
            signing_secret
            or getattr(getattr(db, "settings", None), "supabase_service_key", "")
            or "ask-crump-local-credit-quote-tests"
        )
        self._quote_key = hashlib.sha256(
            f"ask-crump-credit-quotes:{configured_secret}".encode("utf-8")
        ).digest()

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

    def entitled(self, user: dict[str, Any], code: str) -> bool:
        policy = self.policy(code)
        return has_internal_access(user) or self._tier_allowed(tier_name(user), policy.minimum_tier)

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
        if not self.entitled(user, code):
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

    @staticmethod
    def _normalize_components(
        components: dict[str, int] | list[str] | tuple[str, ...],
    ) -> dict[str, int]:
        source = (
            components.items()
            if isinstance(components, dict)
            else ((code, 1) for code in components)
        )
        normalized: dict[str, int] = {}
        for raw_code, raw_quantity in source:
            code = str(raw_code or "").strip().lower()
            if code != MESSAGE_CODE and code not in POLICIES:
                raise FeatureAccessError("Unknown feature.", "UNKNOWN_FEATURE", 400)
            try:
                quantity = int(raw_quantity)
            except (TypeError, ValueError) as exc:
                raise FeatureAccessError(
                    "Invalid quote quantity.", "INVALID_CREDIT_QUOTE", 400
                ) from exc
            if quantity < 1 or quantity > 100:
                raise FeatureAccessError(
                    "Invalid quote quantity.", "INVALID_CREDIT_QUOTE", 400
                )
            normalized[code] = normalized.get(code, 0) + quantity
        if not normalized:
            raise FeatureAccessError(
                "Choose an action to quote.", "INVALID_CREDIT_QUOTE", 400
            )
        return normalized

    async def _usage_count(self, user_id: str, event_type: str) -> int:
        rows = await self.db.select(
            "usage_events",
            columns="id",
            filters={
                "user_id": eq(user_id),
                "event_type": eq(event_type),
                "created_at": gte(day_start_iso()),
            },
            limit=10000,
        )
        return len(rows)

    def _sign_claims(self, claims: dict[str, Any]) -> str:
        payload = json.dumps(
            claims, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        encoded = _urlsafe_encode(payload)
        signature = _urlsafe_encode(
            hmac.new(self._quote_key, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def _scope_digest(self, scope: Any) -> str:
        if scope is None:
            raise FeatureAccessError(
                "Credit review context is unavailable. Start the action again.",
                "CREDIT_SCOPE_REQUIRED",
                409,
            )
        try:
            canonical = json.dumps(
                scope,
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise FeatureAccessError(
                "Credit review context is invalid. Start the action again.",
                "CREDIT_SCOPE_REQUIRED",
                409,
            ) from exc
        return _urlsafe_encode(
            hmac.new(self._quote_key, b"scope:" + canonical, hashlib.sha256).digest()
        )

    def _verify_claims(self, token: str) -> dict[str, Any]:
        try:
            encoded, provided = str(token or "").split(".", 1)
            expected = _urlsafe_encode(
                hmac.new(
                    self._quote_key, encoded.encode("ascii"), hashlib.sha256
                ).digest()
            )
            if not hmac.compare_digest(provided, expected):
                raise ValueError("signature")
            claims = json.loads(_urlsafe_decode(encoded))
            if not isinstance(claims, dict) or int(claims.get("v") or 0) != 1:
                raise ValueError("version")
            if int(claims.get("exp") or 0) < int(time.time()):
                raise ValueError("expired")
            return claims
        except Exception as exc:
            raise FeatureAccessError(
                "That credit quote expired or is invalid. Review the refreshed amount before continuing.",
                "CREDIT_QUOTE_INVALID",
                409,
            ) from exc

    async def quote(
        self,
        user: dict[str, Any],
        components: dict[str, int] | list[str] | tuple[str, ...],
        *,
        message_limit: int | None = None,
        scope: Any = None,
    ) -> dict[str, Any]:
        requested = self._normalize_components(components)
        tier = tier_name(user)
        internal_access = has_internal_access(user)
        credits = await credit_status(self.db, user["id"])
        public_components: list[dict[str, Any]] = []
        claim_components: dict[str, dict[str, int]] = {}
        total = 0

        for code, quantity in requested.items():
            if code == MESSAGE_CODE:
                if message_limit is None:
                    raise FeatureAccessError(
                        "Message allowance is unavailable.",
                        "INVALID_CREDIT_QUOTE",
                        500,
                    )
                label = "Ask Crump message"
                event_type = MESSAGE_CODE
                included = -1 if internal_access else int(message_limit)
                unit_credits = 0 if internal_access else 1
                minimum_tier = "free"
            else:
                policy = self.policy(code)
                if not internal_access and not self._tier_allowed(
                    tier, policy.minimum_tier
                ):
                    raise FeatureAccessError(
                        f"{policy.label} requires a {policy.minimum_tier.title()} plan.",
                        "SUBSCRIPTION_REQUIRED",
                        403,
                        policy.minimum_tier,
                        policy.credit_cost,
                        credits["balance"],
                    )
                label = policy.label
                event_type = f"feature:{code}"
                included = (
                    -1 if internal_access else policy.included_daily[tier]
                )
                unit_credits = 0 if internal_access else policy.credit_cost
                minimum_tier = policy.minimum_tier

            used = (
                0
                if included < 0
                else await self._usage_count(user["id"], event_type)
            )
            remaining = -1 if included < 0 else max(0, included - used)
            included_units = (
                quantity if remaining < 0 else min(quantity, remaining)
            )
            chargeable_units = max(0, quantity - included_units)
            component_credits = chargeable_units * max(0, unit_credits)
            total += component_credits
            claim_components[code] = {
                "q": quantity,
                "max": component_credits,
            }
            public_components.append(
                {
                    "code": code,
                    "label": label,
                    "minimumTier": minimum_tier,
                    "quantity": quantity,
                    "includedRemaining": remaining,
                    "includedUnits": included_units,
                    "chargeableUnits": chargeable_units,
                    "unitCredits": max(0, unit_credits),
                    "credits": component_credits,
                }
            )

        issued_at = int(time.time())
        expires_at = issued_at + QUOTE_TTL_SECONDS
        action_key = str(uuid4())
        claims = {
            "v": 1,
            "sub": str(user["id"]),
            "action": action_key,
            "components": claim_components,
            "total": total,
            "scope": self._scope_digest(scope) if total > 0 else "",
            "iat": issued_at,
            "exp": expires_at,
        }
        draft = next(
            (
                item
                for item in public_components
                if item["code"] == "manuscript_draft"
            ),
            None,
        )
        multi_step = None
        if draft and int(draft["quantity"]) > 1:
            multi_step = {
                "plannedSteps": int(draft["quantity"]),
                "chargeableSteps": int(draft["chargeableUnits"]),
                "perStepCredits": int(draft["unitCredits"]),
                "maximumCredits": int(draft["credits"]),
                "stoppingRule": (
                    "The run stops before it can exceed the approved maximum."
                ),
            }
        return {
            "actionKey": action_key,
            "token": self._sign_claims(claims),
            "includedNow": total == 0,
            "creditsRequired": total,
            "creditBalance": credits["balance"],
            "balanceAfter": max(0, credits["balance"] - total),
            "sufficientBalance": credits["balance"] >= total,
            "components": public_components,
            "multiStep": multi_step,
            "issuedAt": datetime.fromtimestamp(
                issued_at, timezone.utc
            ).isoformat(),
            "expiresAt": datetime.fromtimestamp(
                expires_at, timezone.utc
            ).isoformat(),
        }

    @staticmethod
    def _confirmation_error(
        quote: dict[str, Any], message: str | None = None
    ) -> FeatureAccessError:
        credits = int(quote.get("creditsRequired") or 0)
        balance = int(quote.get("creditBalance") or 0)
        return FeatureAccessError(
            message
            or (
                f"Your included allowance is used. This action will use "
                f"{credits} Crump Credits. Your balance after the action "
                f"will be {max(0, balance - credits)}."
            ),
            "CREDIT_CONFIRMATION_REQUIRED",
            409,
            None,
            credits,
            balance,
            quote,
        )

    async def authorize(
        self,
        user: dict[str, Any],
        components: dict[str, int] | list[str] | tuple[str, ...],
        confirmation: dict[str, Any] | None = None,
        *,
        message_limit: int | None = None,
        scope: Any = None,
    ) -> CreditAuthorization:
        requested = self._normalize_components(components)
        current = await self.quote(
            user,
            requested,
            message_limit=message_limit,
            scope=scope,
        )
        current_total = int(current["creditsRequired"])
        if current_total > int(current["creditBalance"]):
            raise FeatureAccessError(
                f"This action needs {current_total} Crump Credits. "
                f"Your current balance is {current['creditBalance']}.",
                "CREDITS_REQUIRED",
                402,
                None,
                current_total,
                int(current["creditBalance"]),
                current,
            )

        if current_total <= 0 and not confirmation:
            return CreditAuthorization(
                str(user["id"]),
                str(current["actionKey"]),
                {
                    item["code"]: 0
                    for item in current["components"]
                },
                requested,
                0,
            )

        if not isinstance(confirmation, dict):
            raise self._confirmation_error(current)

        try:
            claims = self._verify_claims(
                str(confirmation.get("quoteToken") or "")
            )
        except FeatureAccessError:
            raise self._confirmation_error(
                current,
                "That quote is no longer current. Review the refreshed "
                "credit amount before continuing.",
            )
        if str(claims.get("sub") or "") != str(user["id"]):
            raise self._confirmation_error(
                current, "That quote belongs to a different account."
            )
        if not hmac.compare_digest(
            str(claims.get("scope") or ""),
            self._scope_digest(scope),
        ):
            raise self._confirmation_error(
                current,
                "The action changed. Review the refreshed credit amount.",
            )
        claim_components = (
            claims.get("components")
            if isinstance(claims.get("components"), dict)
            else {}
        )
        claim_quantities = {
            str(code): int(value.get("q") or 0)
            for code, value in claim_components.items()
            if isinstance(value, dict)
        }
        if claim_quantities != requested:
            raise self._confirmation_error(
                current,
                "The action changed. Review the refreshed credit amount.",
            )
        confirmed = int(confirmation.get("confirmedCredits") or -1)
        claimed_total = int(claims.get("total") or 0)
        if confirmed != claimed_total or confirmed <= 0:
            raise self._confirmation_error(current)
        max_by_code = {
            str(code): max(0, int(value.get("max") or 0))
            for code, value in claim_components.items()
            if isinstance(value, dict)
        }
        current_by_code = {
            item["code"]: int(item["credits"])
            for item in current["components"]
        }
        if current_total > confirmed or any(
            current_by_code.get(code, 0) > max_by_code.get(code, 0)
            for code in requested
        ):
            raise self._confirmation_error(
                current,
                "Your account state changed and the current charge is "
                "higher. Review and confirm the new quote.",
            )
        return CreditAuthorization(
            str(user["id"]),
            str(claims.get("action") or current["actionKey"])[:160],
            max_by_code,
            requested,
            confirmed,
        )

    @staticmethod
    def durable_authorization(
        user_id: str,
        *,
        action_key: str,
        code: str,
        approved_limit: int,
        already_spent: int,
    ) -> CreditAuthorization:
        normalized_code = str(code or "").strip().lower()
        normalized_limit = max(0, int(approved_limit or 0))
        normalized_spent = max(0, int(already_spent or 0))
        return CreditAuthorization(
            str(user_id),
            str(action_key or "")[:160],
            {normalized_code: max(0, normalized_limit - normalized_spent)},
            {normalized_code: 1},
            normalized_limit,
            True,
        )

    async def _consume_authorized(
        self,
        user: dict[str, Any],
        code: str,
        *,
        authorization: CreditAuthorization,
        metadata: dict[str, Any] | None = None,
        message_limit: int | None = None,
        instance_key: str | None = None,
        scope: Any = None,
    ) -> dict[str, Any]:
        normalized = str(code or "").strip().lower()
        if str(authorization.user_id) != str(user["id"]):
            raise FeatureAccessError(
                "Credit authorization account mismatch.",
                "CREDIT_QUOTE_INVALID",
                409,
            )
        if normalized == MESSAGE_CODE:
            if message_limit is None:
                raise FeatureAccessError(
                    "Message allowance is unavailable.",
                    "INVALID_CREDIT_QUOTE",
                    500,
                )
            label = "Ask Crump message"
            minimum_tier = "free"
            included = (
                -1 if has_internal_access(user) else int(message_limit)
            )
            credit_cost = 0 if has_internal_access(user) else 1
            event_type = MESSAGE_CODE
            reason = "messages_overflow"
        else:
            policy = await self.require_tier(user, normalized)
            label = policy.label
            minimum_tier = policy.minimum_tier
            included = (
                -1
                if has_internal_access(user)
                else policy.included_daily[tier_name(user)]
            )
            credit_cost = (
                0 if has_internal_access(user) else policy.credit_cost
            )
            event_type = f"feature:{normalized}"
            reason = f"feature_{normalized}"
        credits = await credit_status(self.db, user["id"])
        if has_internal_access(user):
            return {
                "feature": normalized,
                "paymentSource": "internal",
                "eventId": None,
                "creditBalance": credits["balance"],
                "creditsSpent": 0,
                "internalAccess": True,
            }
        if included < 0:
            return {
                "feature": normalized,
                "paymentSource": "subscription",
                "eventId": None,
                "creditBalance": credits["balance"],
                "creditsSpent": 0,
            }

        details = {
            "feature": normalized,
            "creditActionKey": authorization.action_key,
            **(metadata or {}),
        }
        included_result = await self.db.rpc(
            "consume_usage_event",
            {
                "p_user_id": user["id"],
                "p_event_type": event_type,
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
                "feature": normalized,
                "paymentSource": "included",
                "eventId": row.get("event_id"),
                "creditBalance": credits["balance"],
                "creditsSpent": 0,
                "used": int(row.get("used") or 0),
                "limit": included,
            }
        if credit_cost <= 0:
            raise FeatureAccessError(
                f"Your included {label.lower()} allowance is exhausted.",
                "FEATURE_LIMIT_REACHED",
                403,
                minimum_tier,
            )
        if credit_cost > int(
            authorization.max_by_code.get(normalized, 0)
        ):
            if authorization.durable:
                raise FeatureAccessError(
                    "This run reached its approved credit ceiling and "
                    "stopped before another charge.",
                    "CREDIT_BUDGET_EXHAUSTED",
                    409,
                    minimum_tier,
                    credit_cost,
                    credits["balance"],
                )
            fresh = await self.quote(
                user,
                {normalized: 1},
                message_limit=(
                    message_limit if normalized == MESSAGE_CODE else None
                ),
                scope=scope,
            )
            raise self._confirmation_error(
                fresh,
                "Your account state changed and this action now needs "
                "credits. Review the new quote.",
            )

        charge_component = (
            str(instance_key or normalized).strip()[:120] or normalized
        )
        credit_result = await self.db.rpc(
            "spend_credits_confirmed",
            {
                "p_user_id": user["id"],
                "p_amount": credit_cost,
                "p_reason": reason,
                "p_action_key": authorization.action_key,
                "p_component": charge_component,
                "p_confirmed_max": authorization.confirmed_credits,
                "p_metadata": details,
            },
        )
        credit_row = (
            credit_result[0]
            if isinstance(credit_result, list) and credit_result
            else (credit_result or {})
        )
        balance = max(0, int(credit_row.get("balance") or 0))
        if credit_row.get("limit_exceeded"):
            raise FeatureAccessError(
                "This confirmed credit maximum has already been used. Start the action again for a fresh review.",
                "CREDIT_QUOTE_INVALID",
                409,
                minimum_tier,
                credit_cost,
                balance,
            )
        if not credit_row.get("allowed"):
            raise FeatureAccessError(
                f"{label} needs {credit_cost} Crump Credits after "
                "included usage.",
                "CREDITS_REQUIRED",
                402,
                minimum_tier,
                credit_cost,
                balance,
            )
        ledger_id = credit_row.get("ledger_id")
        duplicate = bool(credit_row.get("duplicate"))
        return {
            "feature": normalized,
            "paymentSource": "credits",
            "eventId": f"credit:{ledger_id}" if ledger_id else None,
            "creditBalance": balance,
            "creditsSpent": 0 if duplicate else credit_cost,
            "idempotentReplay": duplicate,
        }

    async def consume(
        self,
        user: dict[str, Any],
        code: str,
        metadata: dict[str, Any] | None = None,
        *,
        confirmation: dict[str, Any] | None = None,
        authorization: CreditAuthorization | None = None,
        instance_key: str | None = None,
        scope: Any = None,
    ) -> dict[str, Any]:
        normalized = str(code or "").strip().lower()
        resolved_scope = (
            scope
            if scope is not None
            else {
                "feature": normalized,
                "instanceKey": str(instance_key or ""),
                "metadata": metadata or {},
            }
        )
        active_authorization = authorization or await self.authorize(
            user,
            {normalized: 1},
            confirmation,
            scope=resolved_scope,
        )
        return await self._consume_authorized(
            user,
            normalized,
            authorization=active_authorization,
            metadata=metadata,
            instance_key=instance_key,
            scope=resolved_scope,
        )

    async def consume_message(
        self,
        user: dict[str, Any],
        *,
        message_limit: int,
        metadata: dict[str, Any] | None = None,
        confirmation: dict[str, Any] | None = None,
        authorization: CreditAuthorization | None = None,
        instance_key: str | None = None,
        scope: Any = None,
    ) -> dict[str, Any]:
        resolved_scope = (
            scope
            if scope is not None
            else {
                "feature": MESSAGE_CODE,
                "instanceKey": str(instance_key or ""),
                "metadata": metadata or {},
            }
        )
        active_authorization = authorization or await self.authorize(
            user,
            {MESSAGE_CODE: 1},
            confirmation,
            message_limit=message_limit,
            scope=resolved_scope,
        )
        return await self._consume_authorized(
            user,
            MESSAGE_CODE,
            authorization=active_authorization,
            metadata=metadata,
            message_limit=message_limit,
            instance_key=instance_key,
            scope=resolved_scope,
        )

    async def refund(self, user_id: str, receipt: dict[str, Any] | None) -> None:
        if not receipt:
            return
        await refund_usage(self.db, user_id, receipt.get("eventId"))
