"""Static and backend contracts for paired guest-admission rate limiting."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from starlette.requests import Request

from backend.rate_limit import RateLimitError, enforce_guest_admission_rate_limit
from backend.security import token_hash


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "migrations" / "20261024024000_atomic_guest_admission_rate_limit.sql"
).read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "postgres-migration-gate.yml").read_text(
    encoding="utf-8"
)


class RpcDb:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def rpc(self, name, payload):
        self.calls.append((name, payload))
        return self.result


def request(ip="203.0.113.7"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/guest",
            "headers": [],
            "query_string": b"",
            "client": (ip, 443),
        }
    )


def test_backend_hashes_both_identifiers_and_uses_one_atomic_rpc():
    database = RpcDb([{"allowed": True, "identity_used": 1, "ip_used": 1}])
    asyncio.run(
        enforce_guest_admission_rate_limit(
            database,
            request(),
            identity="installation:fixture-installation-20261024",
            identity_limit=3,
            ip_limit=20,
            window_seconds=86400,
        )
    )

    assert database.calls == [
        (
            "consume_guest_admission_rate_limit_v1",
            {
                "p_identity_key_hash": token_hash(
                    "auth:guest:identity:installation:fixture-installation-20261024"
                ),
                "p_ip_key_hash": token_hash("auth:guest:ip:203.0.113.7"),
                "p_identity_limit": 3,
                "p_ip_limit": 20,
                "p_window_seconds": 86400,
            },
        )
    ]
    assert "fixture-installation" not in repr(database.calls[0][1].values())
    assert "203.0.113.7" not in repr(database.calls[0][1].values())


@pytest.mark.parametrize("result", [None, [], {}, [{"allowed": False}], "bad"])
def test_backend_fails_closed_on_denial_or_malformed_atomic_result(result):
    database = RpcDb(result)
    with pytest.raises(RateLimitError) as error:
        asyncio.run(
            enforce_guest_admission_rate_limit(
                database,
                request(),
                identity="installation:fixture-installation-20261024",
                identity_limit=3,
                ip_limit=20,
                window_seconds=86400,
            )
        )
    assert error.value.retry_after == 86400
    assert len(database.calls) == 1


def test_backend_preserves_database_retry_after():
    database = RpcDb([{"allowed": False, "retry_after": "37"}])
    with pytest.raises(RateLimitError) as error:
        asyncio.run(
            enforce_guest_admission_rate_limit(
                database,
                request(),
                identity="installation:fixture-installation-20261024",
                identity_limit=3,
                ip_limit=20,
                window_seconds=86400,
            )
        )
    assert error.value.retry_after == 37


def test_migration_is_atomic_service_only_and_rollout_compatible():
    assert "security definer" in MIGRATION
    assert "set search_path = ''" in MIGRATION
    assert "pg_catalog.clock_timestamp()" in MIGRATION
    assert "v_identity_lock < v_ip_lock" in MIGRATION
    assert "v_ip_lock < v_identity_lock" in MIGRATION
    assert "v_identity_scope || ':' || p_identity_key_hash" in MIGRATION
    assert "v_ip_scope || ':' || p_ip_key_hash" in MIGRATION
    assert "insert into public.rate_limit_events (scope, key_hash, created_at)" in MIGRATION
    assert MIGRATION.count("insert into public.rate_limit_events") == 1
    assert "from public, anon, authenticated, service_role" in MIGRATION
    assert "to service_role" in MIGRATION
    assert "unexpected consume_guest_admission_rate_limit_v1 overload" in MIGRATION.lower()


def test_migration_leaves_transaction_control_to_runner_and_has_real_pg17_gate():
    outside_bodies = re.sub(
        r"\$[A-Za-z_]*\$.*?\$[A-Za-z_]*\$|\$\$.*?\$\$",
        "",
        MIGRATION,
        flags=re.DOTALL,
    )
    assert not re.search(
        r"^\s*(?:begin|commit|rollback|start\s+transaction)\b",
        outside_bodies,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert "atomic-guest-admission-rate-limit:" in WORKFLOW
    job = WORKFLOW.split("atomic-guest-admission-rate-limit:", 1)[1].split(
        "\n  legacy-account-deletion-security:", 1
    )[0]
    assert "image: postgres:17" in job
    assert "atomic_guest_admission_rate_limit_baseline.sql" in job
    assert job.count("20261024024000_atomic_guest_admission_rate_limit.sql") == 3
    assert "test_atomic_guest_admission_rate_limit.sql" in job
