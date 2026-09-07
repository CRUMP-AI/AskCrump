from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.feature_service import FeatureAccessError, FeatureService


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
SCOPE = {"fixture": "credit-disclosure"}


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def user(tier: str = "free") -> dict:
    return {
        "id": USER_ID,
        "subscription_tier": tier,
        "subscription_status": "active" if tier != "free" else "inactive",
    }


class CreditDB:
    def __init__(self, *, balance: int = 1000) -> None:
        self.settings = SimpleNamespace(supabase_service_key="test-service-key")
        self.balance = balance
        self.usage: dict[str, int] = {}
        self.ledger: dict[tuple[str, str], dict] = {}
        self.ledger_by_id: dict[str, dict] = {}
        self.sequence = 0

    @staticmethod
    def _filter_value(filters: dict, key: str) -> str:
        value = str(filters.get(key) or "")
        return value[3:] if value.startswith("eq.") else value

    async def select_one(self, table: str, **_options):
        if table == "credit_accounts":
            return {
                "balance": self.balance,
                "lifetime_granted": 1000,
                "lifetime_spent": 1000 - self.balance,
            }
        return None

    async def select(self, table: str, *, filters: dict, **_options):
        if table != "usage_events":
            return []
        event_type = self._filter_value(filters, "event_type")
        return [
            {"id": f"{event_type}-{index}"}
            for index in range(self.usage.get(event_type, 0))
        ]

    async def rpc(self, name: str, params: dict):
        if name == "consume_usage_event":
            event_type = str(params["p_event_type"])
            limit = int(params["p_limit"])
            used = self.usage.get(event_type, 0)
            if limit < 0 or used < limit:
                self.sequence += 1
                self.usage[event_type] = used + 1
                return [{
                    "allowed": True,
                    "event_id": f"usage-{self.sequence}",
                    "used": used + 1,
                }]
            return [{"allowed": False, "event_id": None, "used": used}]

        if name == "spend_credits_confirmed":
            key = (
                str(params["p_action_key"]),
                str(params["p_component"]),
            )
            existing = self.ledger.get(key)
            if existing:
                if existing["refunded"]:
                    return [{
                        "allowed": False,
                        "duplicate": False,
                        "limit_exceeded": True,
                        "ledger_id": None,
                        "balance": self.balance,
                    }]
                return [{
                    "allowed": True,
                    "duplicate": True,
                    "limit_exceeded": False,
                    "ledger_id": existing["id"],
                    "balance": self.balance,
                }]
            amount = int(params["p_amount"])
            confirmed_max = int(params["p_confirmed_max"])
            action_spent = sum(
                int(row["amount"])
                for (action, _component), row in self.ledger.items()
                if action == str(params["p_action_key"])
            )
            if action_spent + amount > confirmed_max:
                return [{
                    "allowed": False,
                    "duplicate": False,
                    "limit_exceeded": True,
                    "ledger_id": None,
                    "balance": self.balance,
                }]
            if self.balance < amount:
                return [{
                    "allowed": False,
                    "duplicate": False,
                    "limit_exceeded": False,
                    "ledger_id": None,
                    "balance": self.balance,
                }]
            self.sequence += 1
            self.balance -= amount
            row = {
                "id": f"ledger-{self.sequence}",
                "amount": amount,
                "refunded": False,
            }
            self.ledger[key] = row
            self.ledger_by_id[row["id"]] = row
            return [{
                "allowed": True,
                "duplicate": False,
                "limit_exceeded": False,
                "ledger_id": row["id"],
                "balance": self.balance,
            }]

        if name == "refund_credit_spend":
            row = self.ledger_by_id.get(str(params["p_ledger_id"]))
            if row and not row["refunded"]:
                row["refunded"] = True
                self.balance += int(row["amount"])
            return [{"balance": self.balance}]

        raise AssertionError(f"Unexpected RPC: {name}")

    async def delete(self, _table: str, **_options):
        return []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected", "tier", "message_limit"),
    [
        ("messages", 1, "free", 1),
        ("research", 1, "free", None),
        ("premium_voice", 2, "professional", None),
        ("visual_analysis", 2, "professional", None),
        ("manuscript_blueprint", 4, "free", None),
        ("image", 6, "professional", None),
        ("manuscript_draft", 8, "free", None),
        ("image_edit", 10, "professional", None),
        ("code_workspace", 12, "professional", None),
        ("video", 60, "professional", None),
        ("video_cinematic_5", 60, "professional", None),
        ("video_extendable", 80, "professional", None),
        ("video_continue", 80, "professional", None),
        ("video_hd", 90, "professional", None),
        ("video_cinematic_10", 120, "enterprise", None),
    ],
)
async def test_server_quotes_every_current_credit_amount(
    code: str, expected: int, tier: str, message_limit: int | None
):
    db = CreditDB()
    event_type = "messages" if code == "messages" else f"feature:{code}"
    db.usage[event_type] = 100
    quote = await FeatureService(db).quote(
        user(tier),
        {code: 1},
        message_limit=message_limit,
        scope=SCOPE,
    )

    assert quote["creditsRequired"] == expected
    assert quote["creditBalance"] == 1000
    assert quote["balanceAfter"] == 1000 - expected
    assert quote["components"] == [
        {
            "code": code,
            "label": quote["components"][0]["label"],
            "minimumTier": quote["components"][0]["minimumTier"],
            "quantity": 1,
            "includedRemaining": 0,
            "includedUnits": 0,
            "chargeableUnits": 1,
            "unitCredits": expected,
            "credits": expected,
        }
    ]


@pytest.mark.asyncio
async def test_included_action_quotes_zero_and_needs_no_confirmation():
    db = CreditDB()
    service = FeatureService(db)
    quote = await service.quote(user(), {"research": 1})
    authorization = await service.authorize(user(), {"research": 1})
    receipt = await service.consume(
        user(),
        "research",
        authorization=authorization,
        instance_key="included-action",
    )

    assert quote["includedNow"] is True
    assert quote["creditsRequired"] == 0
    assert receipt["paymentSource"] == "included"
    assert receipt["creditsSpent"] == 0
    assert db.balance == 1000


@pytest.mark.asyncio
async def test_positive_charge_waits_for_matching_confirmation_and_deduplicates():
    db = CreditDB()
    service = FeatureService(db)
    account = user("professional")

    with pytest.raises(FeatureAccessError) as pending:
        await service.authorize(account, {"image_edit": 1}, scope=SCOPE)
    assert pending.value.code == "CREDIT_CONFIRMATION_REQUIRED"
    assert pending.value.quote["creditsRequired"] == 10
    assert pending.value.quote["balanceAfter"] == 990

    quote = pending.value.quote
    authorization = await service.authorize(
        account,
        {"image_edit": 1},
        {
            "quoteToken": quote["token"],
            "confirmedCredits": quote["creditsRequired"],
        },
        scope=SCOPE,
    )
    first = await service.consume(
        account,
        "image_edit",
        authorization=authorization,
        instance_key="same-action",
    )
    duplicate = await service.consume(
        account,
        "image_edit",
        authorization=authorization,
        instance_key="same-action",
    )

    assert first["creditsSpent"] == 10
    assert first["idempotentReplay"] is False
    assert duplicate["creditsSpent"] == 0
    assert duplicate["idempotentReplay"] is True
    assert duplicate["eventId"] == first["eventId"]
    assert db.balance == 990
    assert len(db.ledger) == 1


@pytest.mark.asyncio
async def test_insufficient_balance_returns_exact_state_without_deduction():
    db = CreditDB(balance=9)
    service = FeatureService(db)

    with pytest.raises(FeatureAccessError) as stopped:
        await service.authorize(
            user("professional"),
            {"image_edit": 1},
            scope=SCOPE,
        )

    assert stopped.value.code == "CREDITS_REQUIRED"
    assert stopped.value.credit_cost == 10
    assert stopped.value.credit_balance == 9
    assert stopped.value.quote["creditsRequired"] == 10
    assert stopped.value.quote["creditBalance"] == 9
    assert stopped.value.quote["sufficientBalance"] is False
    assert db.balance == 9
    assert not db.ledger


@pytest.mark.asyncio
async def test_stale_lower_quote_can_only_charge_the_lower_current_amount():
    db = CreditDB()
    db.usage["feature:research"] = 1
    service = FeatureService(db)
    quote = await service.quote(user(), {"research": 2}, scope=SCOPE)
    assert quote["creditsRequired"] == 2

    db.usage["feature:research"] = 0
    authorization = await service.authorize(
        user(),
        {"research": 2},
        {
            "quoteToken": quote["token"],
            "confirmedCredits": 2,
        },
        scope=SCOPE,
    )
    included = await service.consume(
        user(),
        "research",
        authorization=authorization,
        instance_key="step-1",
    )
    charged = await service.consume(
        user(),
        "research",
        authorization=authorization,
        instance_key="step-2",
    )

    assert included["creditsSpent"] == 0
    assert charged["creditsSpent"] == 1
    assert db.balance == 999


@pytest.mark.asyncio
async def test_stale_higher_quote_requires_a_new_confirmation():
    db = CreditDB()
    service = FeatureService(db)
    quote = await service.quote(user(), {"research": 2}, scope=SCOPE)
    assert quote["creditsRequired"] == 1
    db.usage["feature:research"] = 1

    with pytest.raises(FeatureAccessError) as refreshed:
        await service.authorize(
            user(),
            {"research": 2},
            {
                "quoteToken": quote["token"],
                "confirmedCredits": 1,
            },
            scope=SCOPE,
        )

    assert refreshed.value.code == "CREDIT_CONFIRMATION_REQUIRED"
    assert refreshed.value.quote["creditsRequired"] == 2
    assert db.balance == 1000


@pytest.mark.asyncio
async def test_provider_refund_and_analytics_independence_preserve_balance():
    db = CreditDB()
    service = FeatureService(db)
    account = user("professional")
    quote = await service.quote(account, {"image_edit": 1}, scope=SCOPE)
    authorization = await service.authorize(
        account,
        {"image_edit": 1},
        {
            "quoteToken": quote["token"],
            "confirmedCredits": 10,
        },
        scope=SCOPE,
    )
    receipt = await service.consume(
        account,
        "image_edit",
        authorization=authorization,
        instance_key="provider-attempt",
    )
    assert db.balance == 990

    # FeatureService has no analytics dependency. A provider failure can refund
    # from its durable receipt even when no product-event writer is available.
    await service.refund(USER_ID, receipt)
    assert db.balance == 1000

    with pytest.raises(FeatureAccessError) as replay:
        await service.consume(
            account,
            "image_edit",
            authorization=authorization,
            instance_key="provider-attempt",
        )
    assert replay.value.code == "CREDIT_QUOTE_INVALID"
    assert db.balance == 1000
    assert len(db.ledger) == 1


@pytest.mark.asyncio
async def test_manuscript_quote_discloses_and_enforces_complete_run_ceiling():
    db = CreditDB(balance=200)
    service = FeatureService(db)
    account = user("professional")
    quote = await service.quote(
        account,
        {"manuscript_draft": 5},
        scope=SCOPE,
    )

    assert quote["creditsRequired"] == 24
    assert quote["balanceAfter"] == 176
    assert quote["multiStep"] == {
        "plannedSteps": 5,
        "chargeableSteps": 3,
        "perStepCredits": 8,
        "maximumCredits": 24,
        "stoppingRule": (
            "The run stops before it can exceed the approved maximum."
        ),
    }

    authorization = service.durable_authorization(
        USER_ID,
        action_key="run-budget",
        code="manuscript_draft",
        approved_limit=8,
        already_spent=0,
    )
    first = await service.consume(
        account,
        "manuscript_draft",
        authorization=authorization,
        instance_key="chapter-1",
    )
    second = await service.consume(
        account,
        "manuscript_draft",
        authorization=authorization,
        instance_key="chapter-2",
    )
    third = await service.consume(
        account,
        "manuscript_draft",
        authorization=authorization,
        instance_key="chapter-3",
    )
    with pytest.raises(FeatureAccessError) as ceiling:
        await service.consume(
            account,
            "manuscript_draft",
            authorization=service.durable_authorization(
                USER_ID,
                action_key="run-budget",
                code="manuscript_draft",
                approved_limit=8,
                already_spent=8,
            ),
            instance_key="chapter-4",
        )

    assert first["creditsSpent"] == 0
    assert second["creditsSpent"] == 0
    assert third["creditsSpent"] == 8
    assert ceiling.value.code == "CREDIT_BUDGET_EXHAUSTED"
    assert db.balance == 192


@pytest.mark.asyncio
async def test_confirmation_is_bound_to_the_reviewed_action_scope():
    db = CreditDB()
    db.usage["feature:image_edit"] = 100
    service = FeatureService(db)
    account = user("professional")
    quote = await service.quote(
        account,
        {"image_edit": 1},
        scope={"fileId": "file-a", "instruction": "warm only"},
    )

    with pytest.raises(FeatureAccessError) as changed:
        await service.authorize(
            account,
            {"image_edit": 1},
            {
                "quoteToken": quote["token"],
                "confirmedCredits": 10,
            },
            scope={"fileId": "file-b", "instruction": "replace everything"},
        )

    assert changed.value.code == "CREDIT_CONFIRMATION_REQUIRED"
    assert db.balance == 1000
    assert not db.ledger


@pytest.mark.asyncio
async def test_confirmed_maximum_cannot_be_replayed_across_components():
    db = CreditDB()
    db.usage["feature:image_edit"] = 100
    service = FeatureService(db)
    account = user("professional")
    quote = await service.quote(account, {"image_edit": 1}, scope=SCOPE)
    authorization = await service.authorize(
        account,
        {"image_edit": 1},
        {"quoteToken": quote["token"], "confirmedCredits": 10},
        scope=SCOPE,
    )

    first = await service.consume(
        account,
        "image_edit",
        authorization=authorization,
        instance_key="file-a",
    )
    with pytest.raises(FeatureAccessError) as replay:
        await service.consume(
            account,
            "image_edit",
            authorization=authorization,
            instance_key="file-b",
        )

    assert first["creditsSpent"] == 10
    assert replay.value.code == "CREDIT_QUOTE_INVALID"
    assert db.balance == 990
    assert len(db.ledger) == 1


@pytest.mark.asyncio
async def test_allowance_race_requotes_with_the_original_action_scope():
    db = CreditDB()
    service = FeatureService(db)
    account = user()
    authorization = await service.authorize(
        account,
        {"research": 1},
        scope=SCOPE,
    )
    db.usage["feature:research"] = 1

    with pytest.raises(FeatureAccessError) as refreshed:
        await service.consume(
            account,
            "research",
            authorization=authorization,
            instance_key="research-action",
            scope=SCOPE,
        )

    assert refreshed.value.code == "CREDIT_CONFIRMATION_REQUIRED"
    quote = refreshed.value.quote
    assert quote["creditsRequired"] == 1
    confirmed = await service.authorize(
        account,
        {"research": 1},
        {
            "quoteToken": quote["token"],
            "confirmedCredits": 1,
        },
        scope=SCOPE,
    )
    receipt = await service.consume(
        account,
        "research",
        authorization=confirmed,
        instance_key="research-action",
        scope=SCOPE,
    )
    assert receipt["creditsSpent"] == 1
    assert db.balance == 999


def test_ui_copy_routes_and_fixed_rate_table_match_server_policy():
    confirmation = read("public/credit-confirmation.js")
    billing = read("public/crump-5.2.js")
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    feature_route = read("backend/routes/features.py")

    assert (
        "Your included allowance is used. This action will use "
        in confirmation
    )
    assert "Your balance after the action will be" in confirmation
    assert "${multi ? 'Allow up to' : 'Use'} ${credits.toLocaleString()} credits" in confirmation
    assert "Included now · 0 credits" not in confirmation
    assert "Current overflow rates, after any included allowance:" in billing
    for amount in (1, 2, 4, 6, 8, 10, 12, 60, 80, 90, 120):
        assert str(amount) in billing
    assert "/credit-confirmation.js?v=5.9.76-credit-confirmation-1" in runtime
    assert "/credit-confirmation.js?v=5.9.76-credit-confirmation-1" in worker
    assert 'quote.pop("token", None)' in feature_route
    assert 'quote.pop("actionKey", None)' in feature_route
    for relative in (
        "backend/routes/chat.py",
        "backend/routes/code.py",
        "backend/routes/manuscripts.py",
        "backend/routes/media.py",
        "backend/routes/voice.py",
    ):
        source = read(relative)
        assert "creditConfirmation" in source
        assert "creditQuote" in source
        assert "scope=" in source


def test_false_one_request_one_credit_claim_is_absent():
    for root_name in ("public", "docs", "backend"):
        for path in (ROOT / root_name).rglob("*"):
            if path.is_file() and path.suffix.lower() in {
                ".html", ".js", ".md", ".py", ".txt"
            }:
                source = path.read_text(encoding="utf-8", errors="ignore").lower()
                assert "1 request = 1 credit" not in source
                assert "one request = one credit" not in source


def test_public_credit_copy_covers_premium_and_overflow_without_overclaiming():
    landing = read("public/ask-crump.html")
    billing51 = read("public/crump-billing-5.1.js")
    billing52 = read("public/crump-5.2.js")
    billing_doc = read("docs/BILLING_5_1.md")

    assert (
        "Monthly plans expand included capacity. Some premium or overflow "
        "actions can use Crump Credits. Purchased credits never expire."
        in landing
    )
    for source in (billing51, billing52):
        assert "Some premium or overflow actions use credits." in source
        assert "The exact charge appears before you confirm." in source
    for source in (landing, billing51, billing52, billing_doc):
        normalized = " ".join(source.lower().split())
        assert "take over only after" not in normalized
        assert "used only after included usage is exhausted" not in normalized


def test_video_page_plan_query_is_review_intent_not_cinematic_entitlement():
    video_page = read("public/ai-video-generator.html")
    auth = read("public/auth-controller.js")
    feature_policy = read("backend/feature_service.py")

    assert "plan=professional&amp;intent=video" in video_page
    assert "askcrump.pending-plan-intent" in auth
    assert "crump:plan-intent" in auth
    assert (
        "Creating your account does not start billing; checkout remains a "
        "separate confirmation."
        in auth
    )
    cinematic = feature_policy[feature_policy.index('"video_cinematic_10"'):]
    assert '"enterprise"' in cinematic[:400]
    assert "120" in cinematic[:400]


def test_credit_packs_have_no_unsupported_merchandising_claim():
    billing51 = read("public/crump-billing-5.1.js")
    billing52 = read("public/crump-5.2.js")
    styles = read("public/crump-billing-5.1.css")
    for source in (billing51, billing52):
        lowered = source.lower()
        assert "popular" not in lowered
        assert "most popular" not in lowered
        assert "recommended" not in lowered
        assert "best value" not in lowered
    assert "billing51-pack is-featured" not in billing51
    assert "billing51-pack is-featured" not in billing52
    assert ".billing51-pack.is-featured" not in styles
    assert ".billing51-badge" not in styles
    assert ".billing51-pack.is-featured" not in read("public/crump-v1-body.css")
    assert ".billing51-pack.is-featured" not in read("public/crump-v1.css")
    assert "billing51-plan is-featured" in billing52


def test_confirmed_spend_migration_is_private_idempotent_and_pauses_legacy_runs():
    migration = read("staging/confirmed_feature_spending.sql")
    normalized = " ".join(migration.lower().split())

    for column in (
        "approved_credit_limit",
        "credits_spent",
        "planned_steps",
        "planned_chargeable_steps",
        "credit_per_step",
        "credit_action_key",
    ):
        assert f"add column if not exists {column}" in normalized
    assert "create or replace function public.spend_credits_confirmed" in normalized
    assert "security definer set search_path = ''" in normalized
    assert "pg_advisory_xact_lock" in normalized
    assert "provider = 'feature-spend'" in normalized
    assert "external_id = external_key" in normalized
    assert "return query select existing.id" in normalized
    assert "refund.related_ledger_id = existing.id" in normalized
    assert "p_confirmed_max integer" in normalized
    assert "limit_exceeded boolean" in normalized
    assert "action_spent + p_amount > p_confirmed_max" in normalized
    assert "'confirmedmaximum', p_confirmed_max" in normalized
    assert ") from public, anon, authenticated;" in normalized
    assert ") to service_role;" in normalized
    assert (
        "revoke all on function public.spend_credits( uuid, integer, text, "
        "jsonb ) from service_role;"
    ) in normalized
    assert "credit_budget_confirmation_required" in normalized
    assert "status = 'paused'" in normalized
    assert "credits_spent <= approved_credit_limit" in normalized
    assert not (
        ROOT / "migrations/20260830222959_confirmed_feature_spending.sql"
    ).exists()


def test_credit_release_record_requires_fresh_action_time_migration_identity():
    record = read(
        "docs/CREDIT_CHARGE_DISCLOSURE_RELEASE_ACTION_RECORD_2026-08-30.md"
    )
    normalized = " ".join(record.lower().split())

    assert "staging/confirmed_feature_spending.sql" in normalized
    assert "20260830222959" in normalized
    assert "predates the current live head and is void" in normalized
    assert "supabase migration new confirmed_feature_spending" in normalized
    assert "do not invent or pre-reserve a timestamp" in normalized
    assert "20260901074430 harden_conversation_image_privileges" in normalized
    assert "zero active autopilot manuscript runs" in normalized


def test_application_has_no_caller_for_legacy_unconfirmed_spend():
    callers = []
    for path in (ROOT / "backend").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        callers_only = source.replace("async def consume_usage(", "")
        if "consume_usage(" in callers_only or '"spend_credits"' in source:
            callers.append(str(path.relative_to(ROOT)))
    assert callers == []


def test_private_browser_fixture_covers_safe_credit_states():
    fixture = read("tests/fixtures/credit-charge-disclosure.html")
    for case in (
        "included",
        "positive",
        "insufficient",
        "stale",
        "duplicate",
        "ceiling",
    ):
        assert f'data-case="{case}"' in fixture
    assert "CrumpCreditConfirmation.run" in fixture
    assert "analyticsAvailable: false" in fixture
    assert "No account, provider, analytics service, or credit ledger is connected." in fixture
    assert "askcrump.com" not in fixture
    assert "password" not in fixture.lower()
    assert (ROOT / "scripts/verify-credit-charge-disclosure-browser.cjs").exists()
