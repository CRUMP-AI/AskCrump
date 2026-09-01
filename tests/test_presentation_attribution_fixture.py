from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import Request

from backend.product_analytics import record_account_created_event
from backend.routes import auth as auth_routes
from backend.schemas import CURRENT_TERMS_VERSION, RegisterRequest


EXPECTED_TUPLE = {
    "acquisition": "instagram",
    "placement": "profile-link",
    "campaign": "presentation-proof-current",
    "creative": "ig-feed",
    "intent": "presentation",
}


def fixture_request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("fixture.local", 80),
        "path": "/api/auth/register",
        "query_string": b"",
        "headers": [],
    })


class IsolatedAttributionDB:
    """Minimal application-level fixture for the production registration/RPC contract."""

    def __init__(self) -> None:
        self.users: list[dict] = [{
            "id": "production-control",
            "email": "production-control@example.com",
            "registration_environment": "production",
            "created_at": "2026-09-01T00:00:00+00:00",
            "deleted_at": None,
            "internal_tier": None,
        }]
        self.settings: list[dict] = []
        self.events: list[dict] = [{
            "user_id": "production-control",
            "event_name": "AccountCreated",
            "event_key": "account-created",
            "environment": "production",
            "source": "direct",
            "placement": None,
            "campaign": None,
            "creative": None,
            "intent": None,
            "created_at": "2026-09-01T00:00:00+00:00",
        }]
        self.finance = {"credit_ledger": 7, "media_jobs": 3, "recognized_revenue_cents": 0}

    @staticmethod
    def _filter_value(value: object) -> object:
        if isinstance(value, str) and value.startswith("eq."):
            return value[3:]
        return value

    async def select_one(self, table, **kwargs):
        rows = self.users if table == "users" else self.settings
        filters = kwargs.get("filters") or {}
        for row in rows:
            if all(row.get(key) == self._filter_value(value) for key, value in filters.items()):
                return deepcopy(row)
        return None

    async def insert(self, table, payload):
        assert table == "users"
        self.users.append(deepcopy(payload))
        return [deepcopy(payload)]

    async def upsert(self, table, payload, *, on_conflict):
        assert table == "user_settings"
        assert on_conflict == "user_id"
        self.settings = [row for row in self.settings if row.get("user_id") != payload["user_id"]]
        self.settings.append(deepcopy(payload))
        return [deepcopy(payload)]

    async def update(self, table, payload, *, filters):
        rows = self.users if table == "users" else self.settings
        updated = []
        for row in rows:
            if all(row.get(key) == self._filter_value(value) for key, value in filters.items()):
                row.update(deepcopy(payload))
                updated.append(deepcopy(row))
        return updated

    async def rpc(self, function_name, payload):
        if function_name == "record_account_created_event":
            event = {
                "user_id": payload["p_user_id"],
                "event_name": "AccountCreated",
                "event_key": payload["p_event_key"],
                "environment": payload["p_environment"],
                "source": payload["p_acquisition"],
                "placement": payload["p_placement"],
                "campaign": payload["p_campaign"],
                "creative": payload["p_creative"],
                "intent": payload["p_intent"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            unique_key = (
                event["user_id"], event["event_name"], event["event_key"], event["environment"],
            )
            if any(
                (row["user_id"], row["event_name"], row["event_key"], row["environment"]) == unique_key
                for row in self.events
            ):
                return False
            self.events.append(event)
            return True

        if function_name == "product_weekly_attribution_export":
            environment = payload["p_environment"]
            rows = []
            for user in self.users:
                if user.get("deleted_at") is not None or user.get("registration_environment") != environment:
                    continue
                account_events = [
                    event for event in self.events
                    if event["user_id"] == user["id"]
                    and event["environment"] == environment
                    and event["event_name"] == "AccountCreated"
                ]
                event = account_events[0] if account_events else None
                group = {
                    "acquisition": event.get("source") if event else None,
                    "placement": event.get("placement") if event else None,
                    "campaign": event.get("campaign") if event else None,
                    "creative": event.get("creative") if event else None,
                    "intent": event.get("intent") if event else None,
                }
                existing = next((row for row in rows if all(row[key] == value for key, value in group.items())), None)
                if not existing:
                    existing = {**group, "accounts_created": 0, "account_event_recorded": 0}
                    rows.append(existing)
                existing["accounts_created"] += 1
                existing["account_event_recorded"] += int(event is not None)
            return rows

        if function_name == "delete_user_account":
            user_id = payload["p_user_id"]
            self.users = [row for row in self.users if row["id"] != user_id]
            self.settings = [row for row in self.settings if row["user_id"] != user_id]
            self.events = [row for row in self.events if row["user_id"] != user_id]
            return True

        raise AssertionError(f"Unexpected fixture RPC: {function_name}")

    def production_control(self) -> dict:
        return {
            "users": sum(row.get("registration_environment") == "production" for row in self.users),
            "events": sum(row.get("environment") == "production" for row in self.events),
            "finance": deepcopy(self.finance),
        }

    def account_events(self, *, environment: str) -> list[dict]:
        return [
            row for row in self.events
            if row["environment"] == environment and row["event_name"] == "AccountCreated"
        ]


class FixtureEmail:
    def __init__(self) -> None:
        self.calls = 0

    async def send_verification(self, *_args, **_kwargs):
        self.calls += 1
        return True


@pytest.mark.asyncio
async def test_exact_presentation_first_touch_is_idempotent_exportable_and_cleanable(monkeypatch):
    database = IsolatedAttributionDB()
    fixture_email = FixtureEmail()
    request = fixture_request()
    production_before = database.production_control()

    async def allow_rate_limit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "email_service", fixture_email)
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "hash_password", lambda _password: "fixture-hash")

    assert await database.rpc("product_weekly_attribution_export", {
        "p_since": "2026-09-01T00:00:00Z",
        "p_until": "2026-09-02T00:00:00Z",
        "p_environment": "development",
        "p_include_internal": False,
    }) == []
    assert len(database.account_events(environment="development")) == 0

    registration = await auth_routes.register(
        RegisterRequest(
            email="presentation-fixture@example.com",
            password="FixturePass1234",
            source=EXPECTED_TUPLE["acquisition"],
            placement=EXPECTED_TUPLE["placement"],
            campaign=EXPECTED_TUPLE["campaign"],
            creative=EXPECTED_TUPLE["creative"],
            intent=EXPECTED_TUPLE["intent"],
            termsAccepted=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        request,
    )
    assert registration["success"] is True
    assert fixture_email.calls == 1

    fixture_users = [user for user in database.users if user.get("registration_environment") == "development"]
    assert len(fixture_users) == 1
    fixture_user = fixture_users[0]
    events = database.account_events(environment="development")
    assert len(events) == 1
    assert {
        "acquisition": events[0]["source"],
        "placement": events[0]["placement"],
        "campaign": events[0]["campaign"],
        "creative": events[0]["creative"],
        "intent": events[0]["intent"],
    } == EXPECTED_TUPLE

    first_export = await database.rpc("product_weekly_attribution_export", {
        "p_since": "2026-09-01T00:00:00Z",
        "p_until": "2026-09-02T00:00:00Z",
        "p_environment": "development",
        "p_include_internal": False,
    })
    assert first_export == [{**EXPECTED_TUPLE, "accounts_created": 1, "account_event_recorded": 1}]

    replay_recorded = await record_account_created_event(
        database,
        user_id=fixture_user["id"],
        request=request,
        **EXPECTED_TUPLE,
    )
    assert replay_recorded is False
    assert len(database.account_events(environment="development")) == 1

    pending_registration = await auth_routes.register(
        RegisterRequest(
            email="presentation-fixture@example.com",
            password="FixturePass1234",
            **{
                "source": EXPECTED_TUPLE["acquisition"],
                "placement": EXPECTED_TUPLE["placement"],
                "campaign": EXPECTED_TUPLE["campaign"],
                "creative": EXPECTED_TUPLE["creative"],
                "intent": EXPECTED_TUPLE["intent"],
            },
        ),
        request,
    )
    assert pending_registration["success"] is True
    assert fixture_email.calls == 2
    assert len(database.account_events(environment="development")) == 1

    await database.rpc("delete_user_account", {"p_user_id": fixture_user["id"]})
    assert database.account_events(environment="development") == []
    assert await database.rpc("product_weekly_attribution_export", {
        "p_since": "2026-09-01T00:00:00Z",
        "p_until": "2026-09-02T00:00:00Z",
        "p_environment": "development",
        "p_include_internal": False,
    }) == []
    assert database.production_control() == production_before


def test_fixture_receipt_inputs_are_content_free_and_version_pinned():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    browser_fixture = (root / "tests" / "fixtures" / "presentation-attribution-registration.html").read_text(encoding="utf-8")
    browser_verifier = (root / "scripts" / "verify-presentation-attribution-browser.cjs").read_text(encoding="utf-8")
    combined = browser_fixture + browser_verifier

    assert "presentation-proof-current" in combined
    assert "real-product-continuity" in combined
    assert "Fixture stopped before network account creation." in combined
    assert "https://www.askcrump.com" not in combined
    assert "@gmail.com" not in combined
    assert "window.fetch =" in browser_fixture
    assert "analyticsSent: false" in browser_verifier
    assert (root / "migrations" / "20260830171056_weekly_growth_attribution_export.sql").is_file()
    assert (root / "migrations" / "20260901012708_decision_grade_growth_snapshot.sql").is_file()
