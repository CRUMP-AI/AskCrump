"""Regression contract for the shared guest + registered-Free allowance."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.auth_service import free_text_limit_response
from backend.usage_service import current_usage


ROOT = Path(__file__).resolve().parents[1]
ALLOWANCE_MIGRATION = ROOT / "migrations" / "20261021020000_guest_message_receipts.sql"
GUEST_MIGRATION = ROOT / "migrations" / "20261021003000_guest_mode.sql"


def free_user(*, guest: bool) -> dict:
    return {
        "id": "11111111-1111-5111-8111-111111111111",
        "email": "guest@example.test" if guest else "person@example.test",
        "is_guest": guest,
        "subscription_tier": "free",
        "subscription_status": "inactive",
    }


class UsageDb:
    def __init__(self, created_at: list[str]):
        self.rows = [{"id": f"event-{index}", "created_at": value} for index, value in enumerate(created_at)]
        self.filters = None

    async def select(self, table, columns="*", filters=None, order=None, limit=None):
        assert table == "usage_events"
        assert columns == "id,created_at"
        assert order == "created_at.asc"
        self.filters = filters
        return list(self.rows)

    async def select_one(self, table, columns="*", filters=None):
        assert table == "credit_accounts"
        return None


def settings():
    return SimpleNamespace(
        free_daily_messages=25,
        professional_daily_messages=250,
        enterprise_daily_messages=1000,
    )


def test_guest_and_registered_free_share_identical_rolling_status_contract():
    oldest = datetime.now(timezone.utc) - timedelta(hours=23)
    rows = [(oldest + timedelta(minutes=index)).isoformat() for index in range(5)]
    for guest in (True, False):
        db = UsageDb(rows)
        status = asyncio.run(current_usage(db, free_user(guest=guest), settings()))
        assert status["used"] == 5
        assert status["limit"] == 5
        assert status["remaining"] == 0
        assert status["messageWindowKind"] == "rolling_24h"
        allowance = status["freeMessageAllowance"]
        assert allowance["windowSeconds"] == 86400
        assert allowance["nextAvailableAt"] == (oldest + timedelta(hours=24)).isoformat()
        assert str(db.filters["created_at"]).startswith("gt.")


def test_allowance_reports_the_first_real_slot_when_more_than_five_events_remain():
    oldest = datetime.now(timezone.utc) - timedelta(hours=23)
    for used in (6, 10, 25):
        rows = [(oldest + timedelta(minutes=index)).isoformat() for index in range(used)]
        status = asyncio.run(current_usage(UsageDb(rows), free_user(guest=False), settings()))
        expected_boundary = oldest + timedelta(minutes=used - 5, hours=24)
        assert status["used"] == used
        assert status["remaining"] == 0
        assert status["nextAvailableAt"] == expected_boundary.isoformat()
        assert status["freeMessageAllowance"]["nextAvailableAt"] == expected_boundary.isoformat()


def test_downgraded_paid_user_uses_the_same_exact_free_boundary():
    oldest = datetime.now(timezone.utc) - timedelta(hours=22)
    rows = [(oldest + timedelta(minutes=index)).isoformat() for index in range(6)]
    user = {
        **free_user(guest=False),
        "subscription_tier": "professional",
        "subscription_status": "canceled",
        "subscription_current_period_end": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }
    status = asyncio.run(current_usage(UsageDb(rows), user, settings()))
    assert status["tier"] == "free"
    assert status["nextAvailableAt"] == (oldest + timedelta(minutes=1, hours=24)).isoformat()


def test_limit_response_says_signup_preserves_but_does_not_reset_allowance():
    response = free_text_limit_response(
        free_user(guest=True),
        {"used": 5, "nextAvailableAt": "2026-10-23T12:00:00+00:00"},
    )
    body = json.loads(response.body)
    assert response.status_code == 403
    assert body["code"] == "FREE_TEXT_LIMIT_REACHED"
    assert body["accountRequired"] is True
    assert body["upgradeRequired"] is True
    assert "does not grant another five" in body["message"]
    assert body["freeMessageAllowance"] == {
        "limit": 5,
        "used": 5,
        "remaining": 0,
        "windowKind": "rolling_24h",
        "windowSeconds": 86400,
        "nextAvailableAt": "2026-10-23T12:00:00+00:00",
    }


def test_allowance_migration_is_runner_atomic_service_role_only_and_content_free():
    source = ALLOWANCE_MIGRATION.read_text(encoding="utf-8").lower()
    assert "begin;" not in source
    assert "commit;" not in source
    assert "security definer" in source
    assert "set search_path = ''" in source
    assert "from public, anon, authenticated, service_role" in source
    assert "to service_role" in source
    assert "interval '24 hours'" in source
    assert "v_limit constant integer := 5" in source
    assert "p_limit" not in source
    assert "p_message" not in source.replace("p_message_id", "")
    assert "prompt" not in source
    assert "raw_url" not in source
    assert "event.idempotency_key = v_key" in source
    assert source.index("event.idempotency_key = v_key") < source.index("if v_used >= v_limit")
    assert "'reused'::text,\n      null::uuid" in source
    assert "offset greatest(v_used - v_limit, 0)" in source
    assert "order by event.created_at asc, event.id asc" in source


def test_allowance_migration_samples_database_wall_time_after_the_account_lock():
    source = ALLOWANCE_MIGRATION.read_text(encoding="utf-8").lower()
    lock = source.index("pg_catalog.pg_advisory_xact_lock")
    clock = source.index("v_now := pg_catalog.clock_timestamp();")
    first_window_read = source.index("event.created_at > v_now - interval '24 hours'")

    assert "statement_timestamp()" not in source
    assert "v_now timestamptz;" in source
    assert lock < clock < first_window_read


def test_guest_schema_uses_usage_ledger_not_lifetime_counter():
    source = GUEST_MIGRATION.read_text(encoding="utf-8").lower()
    assert "begin;" not in source
    assert "commit;" not in source
    assert "guest_message_count" not in source
    assert "add column if not exists is_guest" in source


def test_chat_routes_all_effective_free_users_through_one_meter():
    source = (ROOT / "backend" / "routes" / "chat.py").read_text(encoding="utf-8")
    assert "if is_free_text_user(auth.user):" in source
    assert "reserve_free_text_message(" in source
    assert "if not is_free_text_user(auth.user):\n            authorization = await features.authorize(" in source
    assert "reserve_guest_message(" not in source
    assert "GUEST_LIMIT_REACHED" not in source
    assert source.index("result['dailyUsage'] = daily_usage") < source.index("'response_data': result")


def test_guest_creation_does_not_initialize_a_second_counter():
    source = (ROOT / "backend" / "routes" / "auth.py").read_text(encoding="utf-8")
    guest_start = source.index("guest_id = new_uuid()")
    payload_start = source.index("user_payload = {", guest_start)
    guest_payload = source[payload_start:source.index("inserted = await db.insert", payload_start)]
    assert "guest_message_count" not in guest_payload
    assert "'is_guest': True" in guest_payload
