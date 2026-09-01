"""Inspect or safely replace Ask Crump's operator-owned recording account.

The default action is read-only. Replacement is intentionally interactive, uses a
fixed allowlisted identity, removes private Storage objects before account rows,
and never accepts or prints a password on the command line.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from collections.abc import Callable
from datetime import datetime, timezone
import getpass
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_settings  # noqa: E402
from backend.db import SupabaseDB, eq  # noqa: E402
from backend.file_service import FileService  # noqa: E402
from backend.schemas import CURRENT_TERMS_VERSION  # noqa: E402
from backend.security import hash_password, validate_password  # noqa: E402


DEMO_EMAIL = "demo@askcrump.com"
DEMO_NAME = "Ask Crump Demo"
REPLACE_ACKNOWLEDGEMENT = f"REPLACE {DEMO_EMAIL}"
DEMO_RECEIPT_SCHEMA = "ask-crump-demo-clean-state/v1"
DEMO_SETTINGS: dict[str, Any] = {
    "assistant_name": "Crump",
    "work_mode": False,
    "work_start": 9,
    "work_end": 17,
    "preferences": {},
}

# Only presence is inspected. The utility never downloads or displays customer
# content, names, filenames, prompts, messages, or account identifiers.
CONTENT_GROUPS: dict[str, tuple[str, ...]] = {
    "sessions": ("sessions",),
    "conversations": ("user_chats", "message_receipts", "chat_jobs"),
    "files": ("user_files",),
    "projects": ("projects", "project_chats", "project_files", "project_context"),
    "manuscripts": ("manuscripts", "manuscript_sections", "manuscript_runs"),
    "media": ("media_jobs",),
    "code": ("code_tasks", "code_task_events", "code_task_approvals"),
    "intelligence": (
        "user_ai_preferences",
        "user_memories",
        "ai_request_traces",
        "ai_content_reports",
        "chat_memory_opt_outs",
    ),
    "usage": ("usage_events", "credit_accounts", "credit_ledger", "product_events"),
    "notifications": (
        "push_tokens",
        "check_in_preferences",
        "check_in_events",
        "lifecycle_prompt_state",
        "lifecycle_prompt_events",
    ),
}

ACCOUNT_COLUMNS = ",".join(
    (
        "id",
        "email",
        "full_name",
        "profile_picture",
        "preferences",
        "is_verified",
        "subscription_tier",
        "subscription_status",
        "subscription_provider",
        "stripe_customer_id",
        "stripe_subscription_id",
        "store_product_id",
        "internal_tier",
        "registration_environment",
        "deleted_at",
    )
)


class DemoAccountError(RuntimeError):
    """A guarded demo-account operation could not be completed safely."""


def _jwt_role(key: str) -> str | None:
    parts = key.split(".")
    if len(parts) != 3:
        return None
    try:
        encoded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    role = payload.get("role") if isinstance(payload, dict) else None
    return str(role) if role else None


def validate_operator_credentials(supabase_url: str, service_key: str) -> None:
    """Reject public/anonymous credentials before any remote request is made."""
    normalized_url = supabase_url.strip().rstrip("/")
    normalized_key = service_key.strip()
    if not normalized_url.startswith("https://"):
        raise DemoAccountError("SUPABASE_URL must be an HTTPS backend URL.")
    if not normalized_key:
        raise DemoAccountError("SUPABASE_SERVICE_KEY is required.")
    if normalized_key.startswith(("sb_publishable_", "sb_anon_")):
        raise DemoAccountError("A backend-only Supabase service key is required.")
    if not normalized_key.startswith("sb_secret_") and _jwt_role(normalized_key) != "service_role":
        raise DemoAccountError("A backend-only Supabase service key is required.")


def demo_user_payload(*, password_hash: str, now: str, user_id: str) -> dict[str, Any]:
    """Build the fixed internal identity without billing or acquisition evidence."""
    return {
        "id": user_id,
        "email": DEMO_EMAIL,
        "password_hash": password_hash,
        "full_name": DEMO_NAME,
        "is_verified": True,
        "verification_token_hash": None,
        "verification_token_expires": None,
        "password_reset_token_hash": None,
        "password_reset_expires": None,
        "subscription_tier": "free",
        "subscription_status": "inactive",
        "subscription_provider": None,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "store_product_id": None,
        "internal_tier": "enterprise",
        "registration_environment": "preview",
        "preferences": {},
        "terms_accepted_at": now,
        "terms_version": CURRENT_TERMS_VERSION,
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
    }


def is_replaceable_demo_identity(user: dict[str, Any]) -> bool:
    """Protect any non-demo or billing-linked account from this utility."""
    return (
        str(user.get("email") or "").strip().lower() == DEMO_EMAIL
        and str(user.get("full_name") or "").strip() == DEMO_NAME
        and user.get("is_verified") is True
        and str(user.get("subscription_tier") or "").lower() == "free"
        and str(user.get("subscription_status") or "").lower() == "inactive"
        and str(user.get("internal_tier") or "").lower() == "enterprise"
        and str(user.get("registration_environment") or "").lower() == "preview"
        and user.get("deleted_at") is None
        and not any(
            user.get(field)
            for field in (
                "subscription_provider",
                "stripe_customer_id",
                "stripe_subscription_id",
                "store_product_id",
            )
        )
    )


def has_default_demo_profile(
    user: dict[str, Any],
    settings: dict[str, Any] | None,
) -> bool:
    """Verify only content-free profile fields needed for a clean recording state."""
    return (
        user.get("profile_picture") is None
        and user.get("preferences") == {}
        and settings is not None
        and all(settings.get(field) == expected for field, expected in DEMO_SETTINGS.items())
    )


async def inspect_demo_account(db: SupabaseDB) -> dict[str, Any]:
    """Return content-free presence evidence for the fixed demo identity."""
    user = await db.select_one(
        "users",
        columns=ACCOUNT_COLUMNS,
        filters={"email": eq(DEMO_EMAIL)},
    )
    if not user:
        return {
            "exists": False,
            "eligible_for_replace": True,
            "clean": True,
            "profile_defaults": False,
            "ready_for_recording": False,
            "populated_categories": [],
        }

    settings = await db.select_one(
        "user_settings",
        columns=",".join(DEMO_SETTINGS),
        filters={"user_id": eq(user["id"])},
    )
    profile_defaults = has_default_demo_profile(user, settings)

    async def category_has_rows(tables: tuple[str, ...]) -> bool:
        for table in tables:
            rows = await db.select(
                table,
                columns="user_id",
                filters={"user_id": eq(user["id"])},
                limit=1,
            )
            if rows:
                return True
        return False

    populated: list[str] = []
    for category, tables in CONTENT_GROUPS.items():
        if await category_has_rows(tables):
            populated.append(category)
    return {
        "exists": True,
        "eligible_for_replace": is_replaceable_demo_identity(user),
        "clean": not populated,
        "profile_defaults": profile_defaults,
        "ready_for_recording": (
            is_replaceable_demo_identity(user) and profile_defaults and not populated
        ),
        "populated_categories": populated,
    }


async def _remove_private_file_objects(
    db: SupabaseDB,
    files: FileService,
    *,
    user_id: str,
) -> int:
    removed = 0
    while True:
        rows = await db.select(
            "user_files",
            columns="id",
            filters={"user_id": eq(user_id)},
            limit=100,
        )
        if not rows:
            return removed
        for row in rows:
            await files.hard_delete(user_id=user_id, file_id=str(row["id"]))
            removed += 1


async def replace_demo_account(
    db: SupabaseDB,
    files: FileService,
    *,
    password_hash: str,
    now: str | None = None,
    user_id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> dict[str, Any]:
    """Replace only the fixed, protected demo identity and verify it is clean."""
    existing = await db.select_one(
        "users",
        columns=ACCOUNT_COLUMNS,
        filters={"email": eq(DEMO_EMAIL)},
    )
    removed_files = 0
    if existing:
        if not is_replaceable_demo_identity(existing):
            raise DemoAccountError(
                "Replacement blocked: the existing row does not match the protected demo identity."
            )
        existing_id = str(existing["id"])
        removed_files = await _remove_private_file_objects(db, files, user_id=existing_id)
        remaining_files = await db.select(
            "user_files",
            columns="user_id",
            filters={"user_id": eq(existing_id)},
            limit=1,
        )
        if remaining_files:
            raise DemoAccountError("Replacement blocked: private file cleanup is incomplete.")
        await db.rpc("delete_user_account", {"p_user_id": existing_id})
        if await db.select_one("users", columns="id", filters={"email": eq(DEMO_EMAIL)}):
            raise DemoAccountError("Replacement blocked: the previous demo account still exists.")

    timestamp = now or datetime.now(timezone.utc).isoformat()
    payload = demo_user_payload(
        password_hash=password_hash,
        now=timestamp,
        user_id=user_id_factory(),
    )
    inserted = await db.insert("users", payload)
    if isinstance(inserted, list) and inserted:
        created_user_id = str(inserted[0].get("id") or payload["id"])
    else:
        created_user_id = str(payload["id"])
    await db.upsert(
        "user_settings",
        {
            "user_id": created_user_id,
            **DEMO_SETTINGS,
            "updated_at": timestamp,
        },
        on_conflict="user_id",
    )

    inspection = await inspect_demo_account(db)
    if not inspection["ready_for_recording"]:
        raise DemoAccountError("The replacement account did not pass the clean-state verification.")
    return {**inspection, "removed_private_files": removed_files}


def build_clean_state_receipt(
    inspection: dict[str, Any],
    *,
    generated_at: str,
    operation: str,
) -> dict[str, Any]:
    """Build a versioned receipt that contains no account IDs or customer content."""
    if operation not in {"inspection", "replacement"}:
        raise DemoAccountError("The receipt operation is invalid.")
    if not inspection.get("ready_for_recording"):
        raise DemoAccountError("A receipt can be created only for a recording-ready demo account.")
    receipt: dict[str, Any] = {
        "schema": DEMO_RECEIPT_SCHEMA,
        "generated_at": generated_at,
        "operation": operation,
        "demo_identity": DEMO_EMAIL,
        "registration_environment": "preview",
        "internal_account": True,
        "customer_growth_excluded": True,
        "finance_excluded": True,
        "ready_for_recording": True,
        "profile_defaults": True,
        "verified_clean_categories": list(CONTENT_GROUPS),
        "populated_categories": [],
    }
    if operation == "replacement":
        receipt["removed_private_files"] = int(inspection.get("removed_private_files") or 0)
    return receipt


def write_clean_state_receipt(receipt: dict[str, Any], destination: Path) -> None:
    """Create a new receipt without silently overwriting prior evidence."""
    validate_receipt_destination(destination)
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise DemoAccountError("Receipt not written: the destination already exists.") from exc
    except FileNotFoundError as exc:
        raise DemoAccountError("Receipt not written: the destination folder does not exist.") from exc
    except OSError as exc:
        raise DemoAccountError("Receipt not written because the destination is unavailable.") from exc


def validate_receipt_destination(destination: Path) -> None:
    """Fail before remote work when a requested receipt cannot be created safely."""
    if destination.exists():
        raise DemoAccountError("Receipt not written: the destination already exists.")
    if not destination.parent.is_dir():
        raise DemoAccountError("Receipt not written: the destination folder does not exist.")


def format_inspection(inspection: dict[str, Any]) -> str:
    categories = inspection.get("populated_categories") or []
    lines = [
        f"Demo identity: {DEMO_EMAIL}",
        f"Configured: {'yes' if inspection.get('exists') else 'no'}",
        f"Protected identity match: {'yes' if inspection.get('eligible_for_replace') else 'no'}",
        f"Customer-content state: {'clean' if inspection.get('clean') else 'contains demo material'}",
        f"Profile defaults: {'yes' if inspection.get('profile_defaults') else 'no'}",
        f"Recording ready: {'yes' if inspection.get('ready_for_recording') else 'no'}",
        f"Populated categories: {', '.join(categories) if categories else 'none'}",
    ]
    return "\n".join(lines)


def confirmation_is_exact(value: str) -> bool:
    return value == REPLACE_ACKNOWLEDGEMENT


def read_new_password(password_reader: Callable[[str], str] = getpass.getpass) -> str:
    password = password_reader("New demo password (hidden): ")
    valid, error = validate_password(password)
    if not valid:
        raise DemoAccountError(str(error or "The password is invalid."))
    confirmation = password_reader("Repeat new demo password (hidden): ")
    if password != confirmation:
        raise DemoAccountError("The two password entries do not match.")
    return password


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--replace",
        action="store_true",
        help="destructively reset the fixed demo identity after interactive confirmation",
    )
    cli.add_argument(
        "--receipt",
        type=Path,
        help="write a new content-free JSON clean-state receipt to this path",
    )
    return cli


async def run(*, replace: bool, receipt_path: Path | None = None) -> int:
    if receipt_path is not None:
        validate_receipt_destination(receipt_path)
    settings = get_settings()
    validate_operator_credentials(settings.supabase_url, settings.supabase_service_key)
    async with httpx.AsyncClient(timeout=30.0) as client:
        db = SupabaseDB(settings, client=client)
        files = FileService(settings, db)
        inspection = await inspect_demo_account(db)
        print(format_inspection(inspection))
        if not replace:
            if receipt_path is not None:
                receipt = build_clean_state_receipt(
                    inspection,
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    operation="inspection",
                )
                write_clean_state_receipt(receipt, receipt_path)
                print(f"Clean-state receipt written: {receipt_path}")
            print("Read-only inspection complete; no changes were made.")
            return 0
        if inspection["exists"] and not inspection["eligible_for_replace"]:
            raise DemoAccountError(
                "Replacement blocked: the existing row does not match the protected demo identity."
            )

        print(f'Type exactly "{REPLACE_ACKNOWLEDGEMENT}" to continue.')
        if not confirmation_is_exact(input("Confirmation: ")):
            raise DemoAccountError("Replacement cancelled; confirmation did not match.")
        password = read_new_password()
        password_digest = hash_password(password)
        del password
        result = await replace_demo_account(db, files, password_hash=password_digest)
        print(format_inspection(result))
        if receipt_path is not None:
            receipt = build_clean_state_receipt(
                result,
                generated_at=datetime.now(timezone.utc).isoformat(),
                operation="replacement",
            )
            write_clean_state_receipt(receipt, receipt_path)
            print(f"Clean-state receipt written: {receipt_path}")
        print(
            "Replacement complete. The internal preview account is excluded from customer growth cohorts."
        )
        return 0


def main() -> int:
    args = parser().parse_args()
    try:
        return asyncio.run(run(replace=args.replace, receipt_path=args.receipt))
    except (DemoAccountError, EOFError, KeyboardInterrupt) as exc:
        message = str(exc).strip() or "Operation cancelled."
        print(message, file=sys.stderr)
        return 1
    except Exception as exc:
        # Keep remote details, account identifiers, and credentials out of terminal output.
        print(f"Demo account operation failed ({type(exc).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
