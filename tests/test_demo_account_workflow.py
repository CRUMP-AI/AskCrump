from __future__ import annotations

import base64
import json

import pytest

from scripts.manage_demo_account import (
    CONTENT_GROUPS,
    DEMO_EMAIL,
    DEMO_NAME,
    REPLACE_ACKNOWLEDGEMENT,
    DemoAccountError,
    confirmation_is_exact,
    demo_user_payload,
    inspect_demo_account,
    is_replaceable_demo_identity,
    read_new_password,
    replace_demo_account,
    validate_operator_credentials,
)


def service_jwt(role: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.signature"


def protected_user(user_id: str = "old-demo-id") -> dict:
    return {
        "id": user_id,
        "email": DEMO_EMAIL,
        "full_name": DEMO_NAME,
        "is_verified": True,
        "subscription_tier": "free",
        "subscription_status": "inactive",
        "subscription_provider": None,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "store_product_id": None,
        "internal_tier": "enterprise",
        "registration_environment": "preview",
        "deleted_at": None,
    }


class FakeDB:
    def __init__(self, user: dict | None = None, rows: dict[str, list[dict]] | None = None):
        self.user = user
        self.rows = rows or {}
        self.operations: list[tuple] = []

    async def select_one(self, table, *, columns="*", filters=None):
        if table == "users":
            return dict(self.user) if self.user else None
        candidates = await self.select(table, columns=columns, filters=filters, limit=1)
        return candidates[0] if candidates else None

    async def select(self, table, *, columns="*", filters=None, order=None, limit=None):
        candidates = list(self.rows.get(table, []))
        if limit is not None:
            candidates = candidates[:limit]
        return [dict(row) for row in candidates]

    async def rpc(self, function_name, payload, *, retry_transient=False):
        self.operations.append(("rpc", function_name, dict(payload)))
        assert function_name == "delete_user_account"
        self.user = None
        for table in self.rows:
            self.rows[table] = []

    async def insert(self, table, payload):
        self.operations.append(("insert", table, dict(payload)))
        assert table == "users"
        self.user = dict(payload)
        return [dict(payload)]

    async def upsert(self, table, payload, *, on_conflict):
        self.operations.append(("upsert", table, dict(payload), on_conflict))
        return [dict(payload)]


class FakeFiles:
    def __init__(self, db: FakeDB):
        self.db = db
        self.operations: list[tuple[str, str]] = []

    async def hard_delete(self, *, user_id: str, file_id: str):
        self.operations.append((user_id, file_id))
        self.db.rows["user_files"] = [
            row for row in self.db.rows.get("user_files", []) if row["id"] != file_id
        ]


def test_operator_credentials_accept_only_backend_keys():
    validate_operator_credentials("https://example.supabase.co", "sb_secret_backend")
    validate_operator_credentials("https://example.supabase.co", service_jwt("service_role"))

    for key in (
        "",
        "sb_publishable_browser",
        "sb_anon_browser",
        service_jwt("anon"),
        "unknown-key-shape",
    ):
        with pytest.raises(DemoAccountError, match="backend-only|required"):
            validate_operator_credentials("https://example.supabase.co", key)
    with pytest.raises(DemoAccountError, match="HTTPS"):
        validate_operator_credentials("http://example.supabase.co", "sb_secret_backend")


def test_payload_is_internal_preview_verified_and_has_no_billing_identity():
    payload = demo_user_payload(password_hash="secret-hash", now="2026-08-30T12:00:00+00:00", user_id="new-id")

    assert payload["email"] == DEMO_EMAIL
    assert payload["full_name"] == DEMO_NAME
    assert payload["password_hash"] == "secret-hash"
    assert payload["is_verified"] is True
    assert payload["internal_tier"] == "enterprise"
    assert payload["registration_environment"] == "preview"
    assert payload["subscription_tier"] == "free"
    assert payload["subscription_status"] == "inactive"
    for field in (
        "subscription_provider",
        "stripe_customer_id",
        "stripe_subscription_id",
        "store_product_id",
    ):
        assert payload[field] is None


def test_identity_guard_rejects_customer_or_billing_linked_rows():
    assert is_replaceable_demo_identity(protected_user()) is True

    for field, value in (
        ("email", "customer@example.com"),
        ("full_name", "A Customer"),
        ("internal_tier", None),
        ("registration_environment", "production"),
        ("subscription_tier", "enterprise"),
        ("stripe_customer_id", "cus_live"),
        ("deleted_at", "2026-08-30T12:00:00+00:00"),
    ):
        row = protected_user()
        row[field] = value
        assert is_replaceable_demo_identity(row) is False


@pytest.mark.asyncio
async def test_default_inspection_returns_only_category_presence():
    db = FakeDB(
        protected_user(),
        {
            "user_chats": [{"user_id": "old-demo-id", "messages": "private"}],
            "projects": [{"user_id": "old-demo-id", "name": "private"}],
        },
    )

    result = await inspect_demo_account(db)

    assert result == {
        "exists": True,
        "eligible_for_replace": True,
        "clean": False,
        "populated_categories": ["conversations", "projects"],
    }
    serialized = json.dumps(result)
    assert "private" not in serialized
    assert "old-demo-id" not in serialized
    assert set(result) == {"exists", "eligible_for_replace", "clean", "populated_categories"}


@pytest.mark.asyncio
async def test_replacement_removes_storage_first_then_recreates_clean_internal_account():
    rows = {table: [] for tables in CONTENT_GROUPS.values() for table in tables}
    rows["user_files"] = [{"id": "file-one"}, {"id": "file-two"}]
    rows["user_chats"] = [{"user_id": "old-demo-id"}]
    db = FakeDB(protected_user(), rows)
    files = FakeFiles(db)

    result = await replace_demo_account(
        db,
        files,
        password_hash="new-secret-hash",
        now="2026-08-30T12:00:00+00:00",
        user_id_factory=lambda: "new-demo-id",
    )

    assert files.operations == [("old-demo-id", "file-one"), ("old-demo-id", "file-two")]
    assert db.operations[0] == ("rpc", "delete_user_account", {"p_user_id": "old-demo-id"})
    assert db.operations[1][0:2] == ("insert", "users")
    assert db.operations[1][2]["id"] == "new-demo-id"
    assert db.operations[1][2]["password_hash"] == "new-secret-hash"
    assert db.operations[2][0:2] == ("upsert", "user_settings")
    assert result == {
        "exists": True,
        "eligible_for_replace": True,
        "clean": True,
        "populated_categories": [],
        "removed_private_files": 2,
    }


@pytest.mark.asyncio
async def test_replacement_blocks_unsafe_identity_before_any_delete_or_insert():
    unsafe = protected_user()
    unsafe["registration_environment"] = "production"
    db = FakeDB(unsafe, {"user_files": [{"id": "must-remain"}]})
    files = FakeFiles(db)

    with pytest.raises(DemoAccountError, match="protected demo identity"):
        await replace_demo_account(db, files, password_hash="unused")

    assert files.operations == []
    assert db.operations == []
    assert db.rows["user_files"] == [{"id": "must-remain"}]


def test_acknowledgement_and_password_are_interactive_and_exact():
    assert confirmation_is_exact(REPLACE_ACKNOWLEDGEMENT) is True
    assert confirmation_is_exact(REPLACE_ACKNOWLEDGEMENT.lower()) is False
    assert confirmation_is_exact(f" {REPLACE_ACKNOWLEDGEMENT}") is False

    answers = iter(("StrongPassword123", "StrongPassword123"))
    assert read_new_password(lambda _prompt: next(answers)) == "StrongPassword123"

    mismatch = iter(("StrongPassword123", "DifferentPassword456"))
    with pytest.raises(DemoAccountError, match="do not match"):
        read_new_password(lambda _prompt: next(mismatch))
