"""Durable, owner-scoped control plane for Crump Code tasks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from .db import SupabaseDB, eq, gt, in_, lte
from .code_budget import CodeBudgetPolicy, rpc_object
from .feature_service import FeatureAccessError
from .project_service import ProjectService
from .security import normalize_chat_id
from .usage_service import has_internal_access, tier_name


TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
ACTIVE_STATUSES = frozenset(
    {"queued", "provisioning", "running", "awaiting_approval", "verifying"}
)
ACTIVITY_LIMIT = 18
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"provisioning", "cancelled"}),
    "provisioning": frozenset({"running", "queued", "failed", "cancelled"}),
    "running": frozenset({"verifying", "awaiting_approval", "failed", "cancelled"}),
    "awaiting_approval": frozenset({"queued", "failed", "cancelled"}),
    "verifying": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
EVENT_TYPES = frozenset(
    {
        "task.created",
        "task.claimed",
        "sandbox.provisioned",
        "agent.started",
        "tool.requested",
        "tool.completed",
        "verification.started",
        "verification.completed",
        "approval.requested",
        "approval.decided",
        "task.completed",
        "task.failed",
        "task.cancelled",
        "task.requeued",
    }
)
APPROVAL_ACTIONS = frozenset(
    {
        "network_access",
        "credential_access",
        "destructive_source_write",
        "publish",
        "extended_runtime",
    }
)
SAFE_EVENT_KEYS = frozenset(
    {
        "mode",
        "status",
        "tool",
        "path",
        "command",
        "returnCode",
        "changedFiles",
        "verificationCount",
        "failureCode",
        "actionType",
        "decision",
        "durationMs",
    }
)
_REPO_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$")


class CodeTaskError(RuntimeError):
    code = "CODE_TASK_ERROR"
    status_code = 400


class CodeTaskNotFoundError(CodeTaskError):
    code = "CODE_TASK_NOT_FOUND"
    status_code = 404


class CodeTaskConflictError(CodeTaskError):
    code = "CODE_TASK_CONFLICT"
    status_code = 409


class CodeTaskExpiredError(CodeTaskConflictError):
    code = "CODE_TASK_EXPIRED"


class CodeApprovalExpiredError(CodeTaskConflictError):
    code = "CODE_APPROVAL_EXPIRED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _activity_timestamp(task: dict[str, Any]) -> datetime:
    timestamps: list[datetime] = []
    for key in ("created_at", "updated_at", "completed_at"):
        raw = str(task.get(key) or "").strip()
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        timestamps.append(parsed.astimezone(timezone.utc))
    return max(timestamps, default=datetime.min.replace(tzinfo=timezone.utc))


def timestamp_has_passed(value: Any, *, now: datetime | None = None) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return parsed.astimezone(timezone.utc) <= reference.astimezone(timezone.utc)


def _clean_text(value: Any, limit: int) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", " ", str(value or ""))
    return text.strip()[:limit]


def normalize_repo_source(url: Any, revision: Any = None) -> tuple[str, str | None]:
    """Accept only public GitHub HTTPS repository URLs without embedded credentials."""
    raw = str(url or "").strip()
    if not raw or len(raw) > 500:
        raise ValueError("A public GitHub repository URL is required.")
    parsed = urlsplit(raw)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "github.com"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Crump Code currently accepts public https://github.com repositories only.")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 2:
        raise ValueError("Use the root URL of a public GitHub repository.")
    owner, repository = segments
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not _REPO_SEGMENT.fullmatch(owner) or not _REPO_SEGMENT.fullmatch(repository):
        raise ValueError("That GitHub repository URL is not valid.")
    normalized_url = urlunsplit(("https", "github.com", f"/{owner}/{repository}.git", "", ""))

    normalized_ref = str(revision or "").strip() or None
    if normalized_ref:
        if (
            not _REF.fullmatch(normalized_ref)
            or ".." in normalized_ref
            or "//" in normalized_ref
            or normalized_ref.endswith("/")
        ):
            raise ValueError("That Git revision is not valid.")
    return normalized_url, normalized_ref


def sanitize_event_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Keep the audit trail useful without storing prompts, source, output, or secrets."""
    cleaned: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if key not in SAFE_EVENT_KEYS or value is None:
            continue
        if isinstance(value, bool | int | float):
            cleaned[key] = value
        elif isinstance(value, str):
            cleaned[key] = _clean_text(value, 240)
        elif isinstance(value, list):
            cleaned[key] = [_clean_text(item, 160) for item in value[:40]]
    encoded = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 12_000:
        return {}
    return cleaned


class CodeTaskService:
    def __init__(self, db: SupabaseDB, projects: ProjectService) -> None:
        self.db = db
        self.projects = projects

    async def create(
        self,
        *,
        user_id: str,
        project_id: str,
        objective: str,
        mode: str,
        repo_url: str,
        revision: str | None = None,
        max_duration_seconds: int = 180,
    ) -> dict[str, Any]:
        project = await self.projects.get(user_id, project_id)
        clean_objective = _clean_text(objective, 12_000)
        if not clean_objective:
            raise ValueError("Describe what Crump Code should accomplish.")
        normalized_mode = str(mode or "plan").strip().lower()
        if normalized_mode not in {"plan", "implement"}:
            raise ValueError("Crump Code mode must be plan or implement.")
        source_url, source_ref = normalize_repo_source(repo_url, revision)
        duration = max(30, min(240, int(max_duration_seconds or 180)))
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "project_id": project["id"],
            "objective": clean_objective,
            "mode": normalized_mode,
            "source_repo_url": source_url,
            "source_ref": source_ref,
            "status": "queued",
            "network_policy": "deny_all",
            "max_duration_seconds": duration,
            "updated_at": _now(),
        }
        result = await self.db.insert("code_tasks", row)
        task = (result or [row])[0]
        await self.append_event(task, "task.created", {"mode": normalized_mode})
        return task

    async def list(self, *, user_id: str, project_id: str) -> list[dict[str, Any]]:
        project = await self.projects.get(user_id, project_id)
        items = await self.db.select(
            "code_tasks",
            columns=(
                "id,user_id,project_id,objective,mode,source_repo_url,source_ref,status,network_policy,"
                "base_revision,result_summary,failure_code,payment_source,credits_spent,"
                "attempt_count,max_attempts,next_attempt_at,started_at,completed_at,"
                "expires_at,created_at,updated_at,usage_receipt,lease_token"
            ),
            filters={"user_id": eq(user_id), "project_id": eq(project["id"])},
            order="created_at.desc",
            limit=100,
        )
        reconciled: list[dict[str, Any]] = []
        for item in items:
            reconciled.append(await self.reconcile_task_expiry(item))
        return reconciled

    async def list_activity(self, *, user_id: str) -> list[dict[str, Any]]:
        """Return a bounded, content-free activity summary for one account."""
        columns = (
            "id,project_id,status,created_at,updated_at,completed_at,payment_source"
        )
        active = await self.db.select(
            "code_tasks",
            columns=columns,
            filters={
                "user_id": eq(user_id),
                "status": in_(sorted(ACTIVE_STATUSES - {"queued"})),
            },
            order="updated_at.desc",
            limit=ACTIVITY_LIMIT,
        )
        dispatched_queued = await self.db.select(
            "code_tasks",
            columns=columns,
            filters={
                "user_id": eq(user_id),
                "status": eq("queued"),
                "payment_source": "not.is.null",
            },
            order="updated_at.desc",
            limit=ACTIVITY_LIMIT,
        )
        terminal = await self.db.select(
            "code_tasks",
            columns=columns,
            filters={
                "user_id": eq(user_id),
                "status": in_(sorted(TERMINAL_STATUSES)),
            },
            order="completed_at.desc",
            limit=ACTIVITY_LIMIT,
        )

        # A status can change between the bounded reads. Keep the freshest snapshot
        # for each task so an observed completion cannot be hidden by a stale active row.
        # Queued rows are filtered by payment_source in the database so newer prepared
        # drafts cannot consume the query bound and hide real running work.
        newest_by_id: dict[str, dict[str, Any]] = {}
        for item in [*active, *dispatched_queued, *terminal]:
            task_id = str(item.get("id") or "").strip()
            if not task_id:
                continue
            previous = newest_by_id.get(task_id)
            if previous is None or _activity_timestamp(item) >= _activity_timestamp(previous):
                newest_by_id[task_id] = item

        current_active = sorted(
            (
                item
                for item in newest_by_id.values()
                if item.get("status") in ACTIVE_STATUSES
            ),
            key=_activity_timestamp,
            reverse=True,
        )
        recent_terminal = sorted(
            (
                item
                for item in newest_by_id.values()
                if item.get("status") in TERMINAL_STATUSES
            ),
            key=_activity_timestamp,
            reverse=True,
        )
        activity: list[dict[str, Any]] = []
        for item in [*current_active, *recent_terminal]:
            activity.append(self.activity_item(item))
            if len(activity) == ACTIVITY_LIMIT:
                break
        return activity

    async def get(
        self,
        *,
        user_id: str,
        task_id: str,
        include_history: bool = False,
    ) -> dict[str, Any]:
        try:
            normalized = normalize_chat_id(task_id)
        except Exception as exc:
            raise CodeTaskNotFoundError("Crump Code task not found.") from exc
        task = await self.db.select_one(
            "code_tasks", filters={"id": eq(normalized), "user_id": eq(user_id)}
        )
        if not task:
            raise CodeTaskNotFoundError("Crump Code task not found.")
        task = await self.reconcile_task_expiry(task)
        if include_history:
            task = await self._attach_history(task)
            task, reconciled = await self.reconcile_approval_expiry(task)
            if reconciled:
                task = await self._attach_history(task)
        return task

    async def _attach_history(self, task: dict[str, Any]) -> dict[str, Any]:
        detailed = dict(task)
        detailed["events"] = await self.db.select(
            "code_task_events",
            columns="id,event_type,payload,created_at",
            filters={"task_id": eq(task["id"]), "user_id": eq(task["user_id"])},
            order="id.asc",
            limit=500,
        )
        detailed["approvals"] = await self.db.select(
            "code_task_approvals",
            columns="id,action_type,status,title,details,created_at,expires_at,decided_at",
            filters={"task_id": eq(task["id"]), "user_id": eq(task["user_id"])},
            order="created_at.desc",
            limit=100,
        )
        return detailed

    async def append_event(
        self,
        task: dict[str, Any],
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if event_type not in EVENT_TYPES:
            raise ValueError("Unknown Crump Code event type.")
        await self.db.insert(
            "code_task_events",
            {
                "task_id": task["id"],
                "user_id": task["user_id"],
                "project_id": task["project_id"],
                "event_type": event_type,
                "payload": sanitize_event_payload(payload),
            },
        )

    async def transition(
        self,
        task: dict[str, Any],
        target: str,
        *,
        changes: dict[str, Any] | None = None,
        event_type: str | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = str(task.get("status") or "")
        if target not in TRANSITIONS.get(current, frozenset()):
            raise CodeTaskConflictError(f"Crump Code task cannot move from {current} to {target}.")
        payload = {"status": target, "updated_at": _now(), **(changes or {})}
        if target in TERMINAL_STATUSES or target in {"queued", "awaiting_approval"}:
            payload = {"lease_token": None, "lease_expires_at": None, **payload}
        filters = {
            "id": eq(task["id"]),
            "user_id": eq(task["user_id"]),
            "status": eq(current),
        }
        if task.get("lease_token"):
            filters["lease_token"] = eq(task["lease_token"])
        rows = await self.db.update(
            "code_tasks",
            payload,
            filters=filters,
        )
        if not rows:
            raise CodeTaskConflictError("Crump Code task changed while this request was running.")
        updated = rows[0]
        if event_type:
            await self.append_event(updated, event_type, event_payload)
        return updated

    async def claim(
        self,
        task: dict[str, Any],
        *,
        changes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = await self.ensure_not_expired(task)
        return await self.transition(
            task,
            "provisioning",
            changes={
                "started_at": _now(),
                "failure_code": None,
                "next_attempt_at": _now(),
                **(changes or {}),
            },
            event_type="task.claimed",
            event_payload={"status": "provisioning"},
        )

    async def claim_next(self, *, lease_seconds: int, claim_token: str) -> dict[str, Any] | None:
        result = await self.db.rpc(
            "claim_code_task",
            {
                "p_lease_seconds": max(60, min(300, int(lease_seconds))),
                "p_claim_token": claim_token,
            },
            retry_transient=True,
        )
        rows = result if isinstance(result, list) else ([result] if result else [])
        return rows[0] if rows else None

    async def dispatch(
        self,
        task: dict[str, Any],
        *,
        receipt: dict[str, Any],
        dispatch_token: str,
    ) -> dict[str, Any]:
        task = await self.ensure_not_expired(task)
        result = await self.db.rpc(
            "dispatch_code_task",
            {
                "p_task_id": task["id"],
                "p_user_id": task["user_id"],
                "p_dispatch_token": dispatch_token,
                "p_usage_receipt": receipt,
                "p_payment_source": receipt.get("paymentSource"),
                "p_credits_spent": int(receipt.get("creditsSpent") or 0),
            },
            retry_transient=True,
        )
        rows = result if isinstance(result, list) else ([result] if result else [])
        if not rows:
            raise CodeTaskConflictError("Crump Code task is no longer ready to run.")
        return rows[0]

    async def dispatch_authorized(
        self, task: dict[str, Any], *, user: dict[str, Any], features: Any,
        dispatch_token: str, budget_policy: CodeBudgetPolicy,
        confirmation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Authorize a quote, then debit + dispatch in one retry-safe transaction.

        No client receipt or price enters the RPC. Reconcile the durable task
        before authorization so a lost response can be recovered with a new
        HTTP request token, even after its original credit quote expires.
        """
        if str(task.get("user_id")) != str(user.get("id")):
            raise CodeTaskNotFoundError("Crump Code task not found.")

        async def current_task() -> dict[str, Any]:
            current = await self.db.select_one("code_tasks", filters={
                "id": eq(task["id"]), "user_id": eq(user["id"]),
            })
            if not current:
                raise CodeTaskNotFoundError("Crump Code task not found.")
            return current

        current = await current_task()
        if current.get("dispatch_token"):
            return current
        current = await self.ensure_not_expired(current)
        if current.get("status") != "queued":
            raise CodeTaskConflictError("Crump Code task is no longer ready to run.")
        if not isinstance(budget_policy, CodeBudgetPolicy):
            raise ValueError("A validated Code provider policy is required.")
        policy = await features.require_tier(user, "code_workspace")
        usage_key = f"code-task:{current['id']}"
        scope = {"route": "code_task", "taskId": str(current["id"]), "mode": current.get("mode")}
        try:
            authorization = await features.authorize(
                user, {"code_workspace": 1}, confirmation,
                scope=scope, usage_instance_keys={"code_workspace": usage_key},
            )
        except FeatureAccessError:
            # A simultaneous request may already have committed this task while
            # this request was checking its now-stale allowance/quote.
            recovered = await current_task()
            if recovered.get("dispatch_token"):
                return recovered
            raise
        if (str(authorization.user_id) != str(user["id"])
                or authorization.quantities != {"code_workspace": 1}):
            raise CodeTaskConflictError("Code credit authorization does not match this account.")
        internal = has_internal_access(user)
        included = -1 if internal else int(policy.included_daily[tier_name(user)])
        result = rpc_object(await self.db.rpc("reserve_and_dispatch_code_task", {
            "p_task_id": current["id"], "p_user_id": user["id"],
            "p_dispatch_token": dispatch_token, "p_included_limit": included,
            "p_credit_cost": int(policy.credit_cost),
            "p_confirmed_max": int(authorization.max_by_code.get("code_workspace", 0)),
            "p_action_key": authorization.action_key,
            "p_bypass_source": "internal" if internal else "subscription" if included < 0 else None,
            "p_budget_policy": budget_policy.as_dict(),
        }, retry_transient=True))
        if result.get("outcome") in {"dispatched", "replay"} and isinstance(result.get("task"), dict):
            return result["task"]
        if result.get("code") in {"CREDIT_CONFIRMATION_REQUIRED", "CREDITS_REQUIRED"}:
            quote = await features.quote(user, {"code_workspace": 1}, scope=scope,
                                         usage_instance_keys={"code_workspace": usage_key})
            raise FeatureAccessError(
                "Your allowance changed. Review the current Code credit amount before continuing.",
                str(result["code"]), 402 if result["code"] == "CREDITS_REQUIRED" else 409,
                credit_cost=int(policy.credit_cost), credit_balance=int(quote.get("creditBalance") or 0),
                quote=quote,
            )
        raise CodeTaskConflictError("Crump Code task is no longer ready to run.")

    async def refund_if_unstarted(self, task: dict[str, Any]) -> dict[str, Any]:
        """Refund a terminal task only before the first durable provider begin.

        Eligibility, the credit/allowance reversal, and receipt retirement are
        locked in one transaction. Never compose this with FeatureService.refund.
        """
        result = rpc_object(await self.db.rpc("refund_code_task_if_unstarted", {
            "p_task_id": task["id"], "p_user_id": task["user_id"],
        }, retry_transient=True))
        if not isinstance(result.get("task"), dict):
            raise CodeTaskConflictError("Crump Code refund state could not be confirmed.")
        return result["task"]

    async def reconcile_provider_lease(self, task: dict[str, Any]) -> dict[str, Any]:
        """Retire an expired started execution without replay or a credit refund.

        SQL rechecks the current lease deadline under lock, so a concurrent
        valid lease extension cannot be mistaken for an abandoned execution.
        """
        result = rpc_object(await self.db.rpc("reconcile_code_provider_lease", {
            "p_task_id": task["id"], "p_user_id": task["user_id"],
        }, retry_transient=True))
        if not isinstance(result.get("task"), dict):
            raise CodeTaskConflictError("Crump Code provider lease could not be reconciled.")
        return result["task"]

    async def update_fields(self, task: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
        filters = {"id": eq(task["id"]), "user_id": eq(task["user_id"])}
        if task.get("lease_token"):
            filters["lease_token"] = eq(task["lease_token"])
        rows = await self.db.update(
            "code_tasks",
            {**changes, "updated_at": _now()},
            filters=filters,
        )
        if not rows:
            raise CodeTaskConflictError("Crump Code task changed while this request was running.")
        return rows[0]

    async def requeue_after_failure(
        self,
        task: dict[str, Any],
        *,
        failure_code: str,
        delay_seconds: int,
    ) -> dict[str, Any]:
        current = str(task.get("status") or "")
        if current not in {"provisioning", "running", "verifying"}:
            raise CodeTaskConflictError("Crump Code task is no longer retryable.")
        filters = {
            "id": eq(task["id"]),
            "user_id": eq(task["user_id"]),
            "status": eq(current),
            "lease_token": eq(task.get("lease_token")),
        }
        retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(5, min(300, int(delay_seconds)))
        )
        rows = await self.db.update(
            "code_tasks",
            {
                "status": "provisioning",
                "failure_code": _clean_text(failure_code, 80) or "CODE_RUN_FAILED",
                "next_attempt_at": retry_at.isoformat(),
                "lease_token": None,
                "lease_expires_at": None,
                "updated_at": _now(),
            },
            filters=filters,
        )
        if not rows:
            raise CodeTaskConflictError("Crump Code task changed before its retry was saved.")
        updated = rows[0]
        await self.append_event(
            updated,
            "task.requeued",
            {"failureCode": failure_code, "status": "provisioning"},
        )
        return updated

    async def next_refund_pending(self) -> dict[str, Any] | None:
        rows = await self.db.select(
            "code_tasks",
            filters={
                "payment_source": eq("refund_pending"),
                "status": in_(("failed", "cancelled")),
            },
            order="updated_at.asc",
            limit=1,
        )
        return rows[0] if rows else None

    async def mark_refunded(self, task: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.update(
            "code_tasks",
            {
                "usage_receipt": None,
                "payment_source": "refunded",
                "credits_spent": 0,
                "updated_at": _now(),
            },
            filters={
                "id": eq(task["id"]),
                "user_id": eq(task["user_id"]),
                "payment_source": eq("refund_pending"),
            },
        )
        if not rows:
            raise CodeTaskConflictError("Crump Code refund state changed while settling.")
        return rows[0]

    async def reconcile_task_expiry(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status") in TERMINAL_STATUSES or not timestamp_has_passed(task.get("expires_at")):
            return task
        try:
            changes = {
                "failure_code": "CODE_TASK_EXPIRED",
                "completed_at": _now(),
            }
            if task.get("usage_receipt"):
                changes["payment_source"] = "refund_pending"
            return await self.transition(
                task,
                "cancelled",
                changes=changes,
                event_type="task.cancelled",
                event_payload={"failureCode": "CODE_TASK_EXPIRED", "status": "cancelled"},
            )
        except CodeTaskConflictError:
            current = await self.db.select_one(
                "code_tasks",
                filters={"id": eq(task["id"]), "user_id": eq(task["user_id"])},
            )
            if not current:
                raise CodeTaskNotFoundError("Crump Code task not found.")
            return current

    async def ensure_not_expired(self, task: dict[str, Any]) -> dict[str, Any]:
        current = await self.reconcile_task_expiry(task)
        if (
            current.get("status") == "cancelled"
            and current.get("failure_code") == "CODE_TASK_EXPIRED"
        ):
            raise CodeTaskExpiredError(
                "This Crump Code task expired. Prepare a new task to continue."
            )
        return current

    async def _cancel_for_expired_approval(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status") in TERMINAL_STATUSES:
            return task
        try:
            changes = {
                "failure_code": "CODE_APPROVAL_EXPIRED",
                "completed_at": _now(),
            }
            if task.get("usage_receipt"):
                changes["payment_source"] = "refund_pending"
            return await self.transition(
                task,
                "cancelled",
                changes=changes,
                event_type="task.cancelled",
                event_payload={"failureCode": "CODE_APPROVAL_EXPIRED", "status": "cancelled"},
            )
        except CodeTaskConflictError:
            current = await self.db.select_one(
                "code_tasks",
                filters={"id": eq(task["id"]), "user_id": eq(task["user_id"])},
            )
            if not current:
                raise CodeTaskNotFoundError("Crump Code task not found.")
            return current

    async def reconcile_approval_expiry(
        self, task: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        if task.get("status") != "awaiting_approval":
            return task, False
        now = _now()
        changed = False
        expired = False
        for approval in task.get("approvals") or []:
            status = str(approval.get("status") or "")
            if status == "expired":
                expired = True
                continue
            if status != "pending" or not timestamp_has_passed(approval.get("expires_at")):
                continue
            rows = await self.db.update(
                "code_task_approvals",
                {"status": "expired", "decided_at": now},
                filters={
                    "id": eq(approval["id"]),
                    "task_id": eq(task["id"]),
                    "user_id": eq(task["user_id"]),
                    "status": eq("pending"),
                    "expires_at": lte(now),
                },
            )
            if not rows:
                continue
            changed = True
            expired = True
            await self.append_event(
                task,
                "approval.decided",
                {"actionType": rows[0].get("action_type"), "decision": "expired"},
            )
        if expired:
            task = await self._cancel_for_expired_approval(task)
            changed = True
        return task, changed

    async def cancel(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status") in TERMINAL_STATUSES:
            return task
        changes = {"cancel_requested_at": _now(), "completed_at": _now()}
        if task.get("usage_receipt"):
            changes["payment_source"] = "refund_pending"
        return await self.transition(
            task,
            "cancelled",
            changes=changes,
            event_type="task.cancelled",
            event_payload={"status": "cancelled"},
        )

    async def request_approval(
        self,
        task: dict[str, Any],
        *,
        action_type: str,
        title: str,
        details: str = "",
    ) -> dict[str, Any]:
        if action_type not in APPROVAL_ACTIONS:
            raise ValueError("Unknown Crump Code approval type.")
        clean_title = _clean_text(title, 200)
        if not clean_title:
            raise ValueError("Approval title is required.")
        row = {
            "id": str(uuid4()),
            "task_id": task["id"],
            "user_id": task["user_id"],
            "project_id": task["project_id"],
            "action_type": action_type,
            "status": "pending",
            "title": clean_title,
            "details": _clean_text(details, 2000),
        }
        result = await self.db.insert("code_task_approvals", row)
        approval = (result or [row])[0]
        await self.append_event(task, "approval.requested", {"actionType": action_type})
        return approval

    async def decide_approval(
        self,
        *,
        task: dict[str, Any],
        approval_id: str,
        decision: str,
    ) -> dict[str, Any]:
        try:
            normalized = normalize_chat_id(approval_id)
        except Exception as exc:
            raise CodeTaskNotFoundError("Approval request not found.") from exc
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "denied"}:
            raise ValueError("Decision must be approved or denied.")
        decided_at = _now()
        rows = await self.db.update(
            "code_task_approvals",
            {"status": normalized_decision, "decided_at": decided_at},
            filters={
                "id": eq(normalized),
                "task_id": eq(task["id"]),
                "user_id": eq(task["user_id"]),
                "status": eq("pending"),
                "expires_at": gt(decided_at),
            },
        )
        if not rows:
            approval = await self.db.select_one(
                "code_task_approvals",
                filters={
                    "id": eq(normalized),
                    "task_id": eq(task["id"]),
                    "user_id": eq(task["user_id"]),
                },
            )
            if approval and (
                approval.get("status") == "expired"
                or (
                    approval.get("status") == "pending"
                    and timestamp_has_passed(approval.get("expires_at"))
                )
            ):
                if approval.get("status") == "pending":
                    expired_rows = await self.db.update(
                        "code_task_approvals",
                        {"status": "expired", "decided_at": decided_at},
                        filters={
                            "id": eq(normalized),
                            "task_id": eq(task["id"]),
                            "user_id": eq(task["user_id"]),
                            "status": eq("pending"),
                            "expires_at": lte(decided_at),
                        },
                    )
                    if expired_rows:
                        approval = expired_rows[0]
                        await self.append_event(
                            task,
                            "approval.decided",
                            {
                                "actionType": approval.get("action_type"),
                                "decision": "expired",
                            },
                        )
                await self._cancel_for_expired_approval(task)
                raise CodeApprovalExpiredError(
                    "This approval request expired. Prepare a new task to continue."
                )
            raise CodeTaskConflictError("Approval request is no longer pending.")
        await self.append_event(
            task,
            "approval.decided",
            {"actionType": rows[0].get("action_type"), "decision": normalized_decision},
        )
        return rows[0]

    @staticmethod
    def public_task(task: dict[str, Any]) -> dict[str, Any]:
        public = {
            "id", "project_id", "objective", "mode", "source_repo_url", "source_ref",
            "status", "network_policy", "max_duration_seconds", "base_revision",
            "result_summary", "result_patch", "verification", "failure_code",
            "payment_source", "credits_spent", "cancel_requested_at", "started_at",
            "completed_at", "expires_at", "created_at", "updated_at", "attempt_count",
            "max_attempts", "next_attempt_at", "events", "approvals",
        }
        return {key: value for key, value in task.items() if key in public}

    @staticmethod
    def activity_item(task: dict[str, Any]) -> dict[str, Any]:
        """Expose only the fields needed to resume or monitor a task."""
        return {
            "id": task.get("id"),
            "projectId": task.get("project_id"),
            "status": task.get("status"),
            "createdAt": task.get("created_at"),
            "updatedAt": task.get("updated_at"),
            "completedAt": task.get("completed_at"),
        }
