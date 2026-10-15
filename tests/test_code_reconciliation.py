"""Offline maintenance regressions: real expiry service, fake atomic billing seam."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from starlette.requests import Request

from backend.code_reconciliation import reconcile_code_tasks
from backend.code_service import CodeTaskService, TERMINAL_STATUSES
from backend.routes import manuscripts as manuscript_routes


PAST = "2000-01-01T00:00:00+00:00"
FUTURE = "2999-01-01T00:00:00+00:00"
OWNER = "11111111-1111-4111-8111-111111111111"
NEIGHBOR = "22222222-2222-4222-8222-222222222222"
PROJECT = "33333333-3333-4333-8333-333333333333"
PRIVATE = "synthetic-private-objective-not-for-logs"


def task(number: int, *, status="queued", expired=True, owner=OWNER, paid=False, started=False,
         lease_expired=True):
    return {
        "id": str(UUID(int=number)), "user_id": owner, "project_id": PROJECT,
        "status": status, "expires_at": PAST if expired else FUTURE,
        "created_at": PAST, "updated_at": PAST, "failure_code": None,
        "objective": PRIVATE, "source_repo_url": "https://github.com/example/fixture",
        "usage_receipt": {"eventId": f"credit:{UUID(int=number + 1000)}", "paymentSource": "credits"} if paid else None,
        "payment_source": "refund_pending" if paid and status in TERMINAL_STATUSES else "credits" if paid else None,
        "credits_spent": 12 if paid else 0,
        "provider_started_at": PAST if started else None,
        "lease_token": str(UUID(int=number + 2000)),
        "lease_expires_at": PAST if lease_expired else FUTURE,
    }


def approval(number: int, parent: dict, *, expired=True):
    return {
        "id": str(UUID(int=number)), "task_id": parent["id"], "user_id": parent["user_id"],
        "project_id": PROJECT, "status": "pending", "action_type": "extended_runtime",
        "title": "Synthetic bounded extension", "details": PRIVATE,
        "expires_at": PAST if expired else FUTURE, "created_at": PAST,
    }


class MaintenanceDB:
    """Small filter-aware store; no network and no emulation of provider execution.

    Atomic refund and provider-lease reconciliation RPCs are faked. Expiry transitions, audit events,
    ownership predicates, and optimistic state changes use CodeTaskService.
    This does not claim to execute or validate the PostgreSQL transaction itself.
    """

    def __init__(self, tasks=(), approvals=()):
        self.rows = {"code_tasks": deepcopy(list(tasks)), "code_task_approvals": deepcopy(list(approvals)), "code_task_events": []}
        self.calls = []
        self.rpc_calls = []
        self.refund_ledger = []
        self.fail_get = set()
        self.fail_refund = set()
        self.fail_lease = set()
        self.extend_before_lease_lock = set()
        self.provider_holds = {row["id"]: [{"status": "started", "reserved_micros": 6000, "actual_micros": None}]
                               for row in self.rows["code_tasks"] if row.get("provider_started_at")}

    @staticmethod
    def matches(row, filters):
        for key, expression in (filters or {}).items():
            operator, expected = str(expression).split(".", 1)
            actual = row.get(key)
            if operator == "eq" and str(actual) != expected:
                return False
            if operator == "is" and expected == "null" and actual is not None:
                return False
            if operator == "not":
                assert expected == "is.null", "Unexpected fake negated filter"
                if actual is None:
                    return False
            if operator == "in" and actual not in json.loads(f"[{expected[1:-1]}]"):
                return False
            if operator in {"lte", "gt"}:
                if not actual:
                    return False
                left = datetime.fromisoformat(str(actual).replace("Z", "+00:00")).astimezone(timezone.utc)
                right = datetime.fromisoformat(expected.replace("Z", "+00:00")).astimezone(timezone.utc)
                if operator == "lte" and left > right or operator == "gt" and left <= right:
                    return False
        return True

    async def select(self, table, **kwargs):
        self.calls.append(("select", table, deepcopy(kwargs)))
        rows = [row for row in self.rows[table] if self.matches(row, kwargs.get("filters"))]
        if kwargs.get("order"):
            column, direction = kwargs["order"].split(".")
            rows.sort(key=lambda row: str(row.get(column) or ""), reverse=direction == "desc")
        return deepcopy(rows[:kwargs.get("limit", len(rows))])

    async def select_one(self, table, **kwargs):
        self.calls.append(("select_one", table, deepcopy(kwargs)))
        rows = [row for row in self.rows[table] if self.matches(row, kwargs.get("filters"))]
        if rows and rows[0]["id"] in self.fail_get:
            raise RuntimeError(PRIVATE)
        return deepcopy(rows[0]) if rows else None

    async def update(self, table, payload, **kwargs):
        self.calls.append(("update", table, {"payload": deepcopy(payload), **deepcopy(kwargs)}))
        result = []
        for row in self.rows[table]:
            if self.matches(row, kwargs.get("filters")):
                row.update(deepcopy(payload))
                result.append(deepcopy(row))
        return result

    async def insert(self, table, payload):
        assert table == "code_task_events", "Maintenance must not create tasks or execution work"
        row = {"id": len(self.rows[table]) + 1, **deepcopy(payload)}
        self.rows[table].append(row)
        self.calls.append(("insert", table, deepcopy(payload)))
        return [deepcopy(row)]

    async def rpc(self, name, payload, **kwargs):
        assert name in {"refund_code_task_if_unstarted", "reconcile_code_provider_lease"}, "Maintenance must never claim, dispatch, or call a provider"
        assert kwargs == {"retry_transient": True}
        self.rpc_calls.append((name, deepcopy(payload)))
        row = next((item for item in self.rows["code_tasks"] if item["id"] == payload["p_task_id"] and item["user_id"] == payload["p_user_id"]), None)
        assert row is not None, "Atomic maintenance must retain its task owner"
        if name == "reconcile_code_provider_lease":
            # The selected row is a copy; the transaction must re-read its LIVE
            # deadline under lock. This seam models a prior worker extension,
            # not actual PostgreSQL lock/concurrent-connection behavior.
            if row["id"] in self.extend_before_lease_lock:
                row["lease_expires_at"] = FUTURE
            if row["id"] in self.fail_lease:
                raise RuntimeError(PRIVATE)
            now = datetime.now(timezone.utc)
            deadline = row.get("lease_expires_at")
            if (not row.get("provider_started_at") or row["status"] not in {"provisioning", "running", "verifying"}
                    or deadline and datetime.fromisoformat(deadline) > now):
                return {"outcome": "unchanged", "task": deepcopy(row)}
            for hold in self.provider_holds.get(row["id"], []):
                if hold["status"] in {"reserved", "started"}:
                    hold["status"] = "released" if hold["status"] == "reserved" else "uncertain"
            row.update(status="failed", failure_code="CODE_PROVIDER_OUTCOME_UNCERTAIN", lease_token=None,
                       lease_expires_at=None, completed_at=now.isoformat(), updated_at=now.isoformat(),
                       payment_source=(row.get("usage_receipt") or {}).get("paymentSource", "provider_started"))
            self.rows["code_task_events"].append({"id": len(self.rows["code_task_events"]) + 1,
                "task_id": row["id"], "user_id": row["user_id"], "project_id": row["project_id"],
                "event_type": "task.failed", "payload": {"status": "failed", "failureCode": "CODE_PROVIDER_OUTCOME_UNCERTAIN"}})
            return {"outcome": "failed_uncertain", "task": deepcopy(row)}
        if row["id"] in self.fail_refund:
            raise RuntimeError(PRIVATE)
        if row["status"] not in {"cancelled", "failed"}:
            return {"outcome": "not_terminal", "task": deepcopy(row)}
        if row.get("provider_started_at"):
            row["payment_source"] = (row.get("usage_receipt") or {}).get("paymentSource", "provider_started")
            return {"outcome": "provider_started", "task": deepcopy(row)}
        if row.get("payment_source") == "refunded" or not row.get("usage_receipt"):
            return {"outcome": "no_receipt", "task": deepcopy(row)}
        self.refund_ledger.append((row["user_id"], row["id"], row["credits_spent"]))
        row.update(payment_source="refunded", usage_receipt=None, credits_spent=0)
        return {"outcome": "refunded", "task": deepcopy(row)}

    def get_row(self, task_id):
        return next(row for row in self.rows["code_tasks"] if row["id"] == task_id)


class ObservedTaskService(CodeTaskService):
    def __init__(self, database):
        super().__init__(database, SimpleNamespace())
        self.detail_calls = []

    async def get(self, **kwargs):
        self.detail_calls.append(dict(kwargs))
        return await super().get(**kwargs)


@pytest.mark.asyncio
async def test_maintenance_expires_abandoned_task_without_owner_or_paid_execution():
    expired = task(1, paid=True)
    live = task(2, expired=False)
    db = MaintenanceDB([expired, live])
    service = ObservedTaskService(db)

    summary = await reconcile_code_tasks(db, service)

    assert db.get_row(expired["id"])["status"] == "cancelled"
    assert db.get_row(expired["id"])["failure_code"] == "CODE_TASK_EXPIRED"
    assert db.get_row(expired["id"])["completed_at"]
    assert db.get_row(live["id"])["status"] == "queued"
    assert summary == {"scanned": 1, "cancelled": 1, "refundsScanned": 1, "refunded": 1, "costRetained": 0,
                       "leasesScanned": 0, "leasesRetired": 0, "errors": 0, "timedOut": False}
    assert db.refund_ledger == [(OWNER, expired["id"], 12)]
    assert [event["event_type"] for event in db.rows["code_task_events"]] == ["task.cancelled"]
    assert PRIVATE not in json.dumps(summary)


@pytest.mark.asyncio
async def test_maintenance_expires_pending_approval_even_when_owner_never_returns():
    waiting = task(3, status="awaiting_approval", expired=False, paid=True)
    pending = approval(300, waiting)
    db = MaintenanceDB([waiting], [pending])

    summary = await reconcile_code_tasks(db, CodeTaskService(db, SimpleNamespace()))

    assert db.rows["code_task_approvals"][0]["status"] == "expired"
    assert db.get_row(waiting["id"])["status"] == "cancelled"
    assert db.get_row(waiting["id"])["failure_code"] == "CODE_APPROVAL_EXPIRED"
    assert summary["cancelled"] == 1
    assert summary["refunded"] == 1
    assert [event["event_type"] for event in db.rows["code_task_events"]] == ["approval.decided", "task.cancelled"]


@pytest.mark.asyncio
async def test_live_approval_stays_pending_and_discovery_deduplicates_owner_task_pair():
    expired_waiting = task(4, status="awaiting_approval")
    live_waiting = task(5, status="awaiting_approval", expired=False, owner=NEIGHBOR)
    db = MaintenanceDB([expired_waiting, live_waiting], [approval(500, live_waiting, expired=False)])
    service = ObservedTaskService(db)

    summary = await reconcile_code_tasks(db, service, refund_limit=0)

    assert summary["scanned"] == 2  # Expired waiting task appeared in both discovery queries.
    assert len(service.detail_calls) == 2
    assert {(call["user_id"], call["task_id"]) for call in service.detail_calls} == {(OWNER, expired_waiting["id"]), (NEIGHBOR, live_waiting["id"])}
    assert db.get_row(live_waiting["id"])["status"] == "awaiting_approval"
    assert db.rows["code_task_approvals"][0]["status"] == "pending"
    assert summary["cancelled"] == 1
    assert not db.rpc_calls
    for method, table, payload in db.calls:
        if method in {"select_one", "update"}:
            filters = payload["filters"]
            assert filters["user_id"] in {f"eq.{OWNER}", f"eq.{NEIGHBOR}"}
            assert "id" in filters


@pytest.mark.asyncio
async def test_atomic_refund_only_unstarted_terminal_tasks_retains_provider_cost_and_retries_idempotently():
    unused = task(6, status="cancelled", paid=True)
    spent = task(7, status="failed", paid=True, started=True, owner=NEIGHBOR)
    running = task(8, status="running", expired=False, paid=True)
    running["payment_source"] = "refund_pending"  # The scan must still exclude active work.
    completed = task(9, status="completed", paid=True)
    db = MaintenanceDB([unused, spent, running, completed])
    service = CodeTaskService(db, SimpleNamespace())

    first = await reconcile_code_tasks(db, service)
    second = await reconcile_code_tasks(db, service)

    assert first["refundsScanned"] == 3
    assert first["refunded"] == 1
    assert first["costRetained"] == 1
    assert second["refunded"] == 0
    assert db.refund_ledger == [(OWNER, unused["id"], 12)]
    assert db.get_row(spent["id"])["payment_source"] == "credits"
    assert db.get_row(spent["id"])["credits_spent"] == 12
    assert db.get_row(spent["id"])["usage_receipt"] == spent["usage_receipt"]
    assert db.get_row(running["id"])["status"] == "running"
    assert db.get_row(completed["id"])["payment_source"] == "refund_pending"
    assert all(payload["p_task_id"] != running["id"] for _name, payload in db.rpc_calls)
    assert ("refund_code_task_if_unstarted", {"p_task_id": spent["id"], "p_user_id": NEIGHBOR}) in db.rpc_calls


@pytest.mark.asyncio
async def test_discovery_and_refund_work_are_bounded_even_for_oversized_requested_limits():
    expired = [task(100 + i) for i in range(100)]
    waiting = [task(300 + i, status="awaiting_approval", expired=False) for i in range(100)]
    refunds = [task(500 + i, status="failed", paid=True) for i in range(50)]
    db = MaintenanceDB([*expired, *waiting, *refunds])

    summary = await reconcile_code_tasks(db, CodeTaskService(db, SimpleNamespace()), limit=10000, refund_limit=10000)

    discovery = [kwargs for method, table, kwargs in db.calls if method == "select" and table == "code_tasks"]
    assert [query["limit"] for query in discovery] == [40, 40, 40, 20]
    assert summary["scanned"] == 80
    assert summary["cancelled"] == 40
    assert summary["refundsScanned"] == summary["refunded"] == 20
    assert len(db.refund_ledger) == 20


@pytest.mark.asyncio
async def test_started_leases_filter_before_limit_avoids_unused_lease_starvation_and_retains_costs():
    # Fifty older unused leases must not consume a two-row scan before the
    # started marker is applied. General task expiry is still in the future.
    unused = [task(2000 + i, status="provisioning", expired=False) for i in range(50)]
    retired = [task(2100 + i, status=phase, expired=False, paid=True, started=True)
               for i, phase in enumerate(("running", "verifying"))]
    live = task(2110, status="running", expired=False, paid=True, started=True, lease_expired=False)
    terminal = task(2111, status="completed", expired=False, paid=True, started=True)
    terminal["payment_source"] = "credits"
    db = MaintenanceDB([*unused, *retired, live, terminal])
    # Make unused rows sort before started work by their actual stale deadlines.
    for row in db.rows["code_tasks"][:50]:
        row["lease_expires_at"] = "1990-01-01T00:00:00+00:00"
    for row in retired:
        db.provider_holds[row["id"]].append({"status": "reserved", "reserved_micros": 2000, "actual_micros": None})
    service = CodeTaskService(db, SimpleNamespace())

    summary = await reconcile_code_tasks(db, service, limit=2)

    scan = next(kwargs for method, table, kwargs in db.calls if method == "select" and table == "code_tasks"
                and kwargs["filters"].get("provider_started_at"))
    assert scan["filters"]["provider_started_at"] == "not.is.null"
    assert scan["limit"] == 2
    assert summary["leasesScanned"] == summary["leasesRetired"] == 2
    assert summary["scanned"] == summary["refundsScanned"] == summary["refunded"] == summary["errors"] == 0
    assert not db.refund_ledger
    assert {payload["p_task_id"] for name, payload in db.rpc_calls if name == "reconcile_code_provider_lease"} == {row["id"] for row in retired}
    assert not any(name == "refund_code_task_if_unstarted" for name, _ in db.rpc_calls)
    for original in retired:
        row = db.get_row(original["id"])
        assert row["status"] == "failed" and row["failure_code"] == "CODE_PROVIDER_OUTCOME_UNCERTAIN"
        assert row["lease_token"] is row["lease_expires_at"] is None
        assert row["provider_started_at"] == original["provider_started_at"]
        assert row["usage_receipt"] == original["usage_receipt"] and row["credits_spent"] == 12
        assert row["payment_source"] == "credits"
        assert db.provider_holds[row["id"]] == [
            {"status": "uncertain", "reserved_micros": 6000, "actual_micros": None},
            {"status": "released", "reserved_micros": 2000, "actual_micros": None},
        ]
    assert db.get_row(live["id"])["status"] == "running"
    assert db.get_row(terminal["id"])["status"] == "completed"
    assert all(db.get_row(row["id"])["status"] == "provisioning" for row in unused)
    assert [event["event_type"] for event in db.rows["code_task_events"]] == ["task.failed", "task.failed"]
    second = await reconcile_code_tasks(db, service, limit=2)
    assert second["leasesScanned"] == second["leasesRetired"] == 0
    assert len(db.rows["code_task_events"]) == 2


@pytest.mark.asyncio
async def test_lease_lock_rechecks_live_extension_and_one_failed_row_does_not_block_later_retirement(caplog):
    bad, extended, expired = [task(2200 + i, status="running", expired=False, paid=True, started=True)
                              for i in range(3)]
    db = MaintenanceDB([bad, extended, expired])
    db.fail_lease.add(bad["id"])
    db.extend_before_lease_lock.add(extended["id"])

    summary = await reconcile_code_tasks(db, CodeTaskService(db, SimpleNamespace()))

    assert summary["leasesScanned"] == 3
    assert summary["leasesRetired"] == summary["errors"] == 1
    assert summary["refundsScanned"] == summary["refunded"] == 0
    assert db.get_row(bad["id"])["status"] == "running"
    assert db.get_row(extended["id"])["status"] == "running"
    assert db.get_row(extended["id"])["lease_expires_at"] == FUTURE
    assert db.provider_holds[extended["id"]][0]["status"] == "started"
    assert db.get_row(expired["id"])["status"] == "failed"
    assert db.provider_holds[expired["id"]][0]["status"] == "uncertain"
    assert not db.refund_ledger
    assert [event["task_id"] for event in db.rows["code_task_events"]] == [expired["id"]]
    assert "Code lease settlement deferred error_type=RuntimeError" in caplog.text
    assert PRIVATE not in caplog.text and OWNER not in caplog.text and "github.com" not in caplog.text


@pytest.mark.asyncio
async def test_one_bad_task_and_refund_do_not_block_later_rows_or_expose_content(caplog):
    bad_get, good_get = task(10), task(11)
    bad_refund = task(12, status="failed", paid=True)
    good_refund = task(13, status="failed", paid=True)
    retained = task(14, status="failed", paid=True, started=True)
    db = MaintenanceDB([bad_get, good_get, bad_refund, good_refund, retained])
    db.fail_get.add(bad_get["id"])
    db.fail_refund.add(bad_refund["id"])

    summary = await reconcile_code_tasks(db, CodeTaskService(db, SimpleNamespace()))

    assert summary["errors"] == 2
    assert summary["cancelled"] == summary["refunded"] == summary["costRetained"] == 1
    assert summary["refundsScanned"] == 3
    assert db.get_row(good_get["id"])["status"] == "cancelled"
    assert db.get_row(good_refund["id"])["payment_source"] == "refunded"
    assert "error_type=RuntimeError" in caplog.text
    assert PRIVATE not in caplog.text
    assert OWNER not in caplog.text
    assert "github.com" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["discovery", "detail", "lease", "refund"])
async def test_one_global_deadline_cancels_stalled_io_and_returns_partial_metrics(phase):
    row = task(15, status="failed", paid=True) if phase == "refund" else (
        task(15, status="running", expired=False, paid=True, started=True) if phase == "lease" else task(15))
    db = MaintenanceDB([row])
    service = CodeTaskService(db, SimpleNamespace())
    cancellation = asyncio.Event()

    async def stall(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancellation.set()

    if phase == "discovery":
        db.select = stall
    elif phase == "detail":
        service.get = stall
    else:
        db.rpc = stall

    summary = await asyncio.wait_for(reconcile_code_tasks(db, service, timeout_seconds=.01), timeout=1.0)

    assert summary["timedOut"] is True
    assert summary["errors"] == 0
    assert cancellation.is_set()
    assert summary["scanned"] == (1 if phase == "detail" else 0)
    assert summary["refundsScanned"] == (1 if phase == "refund" else 0)
    assert summary["leasesScanned"] == (1 if phase == "lease" else 0)
    assert summary["leasesRetired"] == 0
    assert not db.refund_ledger


@pytest.mark.asyncio
async def test_discovery_failure_returns_content_free_error_metrics(caplog):
    async def fail(*_args, **_kwargs):
        raise OSError(PRIVATE)

    db = SimpleNamespace(select=fail)
    service = SimpleNamespace(get=AsyncMock(), refund_if_unstarted=AsyncMock())

    summary = await reconcile_code_tasks(db, service)

    assert summary["errors"] == 1
    assert summary["scanned"] == summary["refundsScanned"] == 0
    service.get.assert_not_awaited()
    service.refund_if_unstarted.assert_not_awaited()
    assert "error_type=OSError" in caplog.text
    assert PRIVATE not in caplog.text


def cron_request(authorization=""):
    return Request({"type": "http", "method": "GET", "path": "/api/cron/manuscripts", "headers": [(b"authorization", authorization.encode())]})


@pytest.mark.asyncio
@pytest.mark.parametrize("secret,authorization", [("local-cron-secret", ""), ("local-cron-secret", "Bearer wrong"), (None, "Bearer local-cron-secret")])
async def test_unauthorized_cron_does_zero_queries_or_worker_calls(monkeypatch, secret, authorization):
    db = MaintenanceDB([task(16)])
    deletion = SimpleNamespace(process_next=AsyncMock())
    worker = SimpleNamespace(process_next=AsyncMock())
    manuscripts = SimpleNamespace(process_next_run=AsyncMock())
    monkeypatch.setattr(manuscript_routes, "settings", SimpleNamespace(cron_secret=secret, vercel_oidc_token=None, code_workspace_enabled=False))
    monkeypatch.setattr(manuscript_routes, "db", db)
    monkeypatch.setattr(manuscript_routes, "code_tasks", CodeTaskService(db, SimpleNamespace()))
    monkeypatch.setattr(manuscript_routes, "account_deletions", deletion)
    monkeypatch.setattr(manuscript_routes, "code_worker", worker)
    monkeypatch.setattr(manuscript_routes, "manuscripts", manuscripts)

    response = await manuscript_routes.manuscript_cron(cron_request(authorization))

    assert response.status_code == 401
    assert not db.calls
    assert not db.rpc_calls
    deletion.process_next.assert_not_awaited()
    worker.process_next.assert_not_awaited()
    manuscripts.process_next_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_closed_code_feature_still_reconciles_before_account_deletion_early_return(monkeypatch):
    expired = task(17, paid=True)
    db = MaintenanceDB([expired])

    async def deletion_after_maintenance():
        assert db.get_row(expired["id"])["status"] == "cancelled"
        assert db.get_row(expired["id"])["payment_source"] == "refunded"
        return {"handled": True, "status": "completed"}

    deletion = SimpleNamespace(process_next=AsyncMock(side_effect=deletion_after_maintenance))
    worker = SimpleNamespace(process_next=AsyncMock())
    manuscripts = SimpleNamespace(process_next_run=AsyncMock())
    monkeypatch.setattr(manuscript_routes, "settings", SimpleNamespace(cron_secret="local-cron-secret", vercel_oidc_token=None, code_workspace_enabled=False))
    monkeypatch.setattr(manuscript_routes, "db", db)
    monkeypatch.setattr(manuscript_routes, "code_tasks", CodeTaskService(db, SimpleNamespace()))
    monkeypatch.setattr(manuscript_routes, "account_deletions", deletion)
    monkeypatch.setattr(manuscript_routes, "code_worker", worker)
    monkeypatch.setattr(manuscript_routes, "manuscripts", manuscripts)

    result = await manuscript_routes.manuscript_cron(cron_request("Bearer local-cron-secret"))

    assert result["worker"] == "account-storage-deletion"
    assert result["codeMaintenance"]["cancelled"] == result["codeMaintenance"]["refunded"] == 1
    assert result["codeMaintenance"]["errors"] == 0
    deletion.process_next.assert_awaited_once()
    worker.process_next.assert_not_awaited()
    manuscripts.process_next_run.assert_not_awaited()
