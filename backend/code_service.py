"""Durable, owner-scoped control plane for Crump Code tasks."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from .db import SupabaseDB, eq
from .project_service import ProjectService
from .security import normalize_chat_id


TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
ACTIVE_STATUSES = frozenset(
    {"queued", "provisioning", "running", "awaiting_approval", "verifying"}
)
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        return await self.db.select(
            "code_tasks",
            columns=(
                "id,project_id,objective,mode,source_repo_url,source_ref,status,network_policy,"
                "base_revision,result_summary,failure_code,payment_source,credits_spent,"
                "started_at,completed_at,expires_at,created_at,updated_at"
            ),
            filters={"user_id": eq(user_id), "project_id": eq(project["id"])},
            order="created_at.desc",
            limit=100,
        )

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
        if include_history:
            task = dict(task)
            task["events"] = await self.db.select(
                "code_task_events",
                columns="id,event_type,payload,created_at",
                filters={"task_id": eq(normalized), "user_id": eq(user_id)},
                order="id.asc",
                limit=500,
            )
            task["approvals"] = await self.db.select(
                "code_task_approvals",
                columns="id,action_type,status,title,details,created_at,expires_at,decided_at",
                filters={"task_id": eq(normalized), "user_id": eq(user_id)},
                order="created_at.desc",
                limit=100,
            )
        return task

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
        rows = await self.db.update(
            "code_tasks",
            payload,
            filters={
                "id": eq(task["id"]),
                "user_id": eq(task["user_id"]),
                "status": eq(current),
            },
        )
        if not rows:
            raise CodeTaskConflictError("Crump Code task changed while this request was running.")
        updated = rows[0]
        if event_type:
            await self.append_event(updated, event_type, event_payload)
        return updated

    async def claim(self, task: dict[str, Any]) -> dict[str, Any]:
        return await self.transition(
            task,
            "provisioning",
            changes={"started_at": _now(), "failure_code": None},
            event_type="task.claimed",
            event_payload={"status": "provisioning"},
        )

    async def update_fields(self, task: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
        rows = await self.db.update(
            "code_tasks",
            {**changes, "updated_at": _now()},
            filters={"id": eq(task["id"]), "user_id": eq(task["user_id"])},
        )
        if not rows:
            raise CodeTaskConflictError("Crump Code task changed while this request was running.")
        return rows[0]

    async def cancel(self, task: dict[str, Any]) -> dict[str, Any]:
        if task.get("status") in TERMINAL_STATUSES:
            return task
        return await self.transition(
            task,
            "cancelled",
            changes={"cancel_requested_at": _now(), "completed_at": _now()},
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
        rows = await self.db.update(
            "code_task_approvals",
            {"status": normalized_decision, "decided_at": _now()},
            filters={
                "id": eq(normalized),
                "task_id": eq(task["id"]),
                "user_id": eq(task["user_id"]),
                "status": eq("pending"),
            },
        )
        if not rows:
            raise CodeTaskConflictError("Approval request is no longer pending.")
        await self.append_event(
            task,
            "approval.decided",
            {"actionType": rows[0].get("action_type"), "decision": normalized_decision},
        )
        return rows[0]

    @staticmethod
    def public_task(task: dict[str, Any]) -> dict[str, Any]:
        hidden = {
            "user_id",
            "sandbox_name",
            "sandbox_session_id",
            "base_snapshot_id",
            "final_snapshot_id",
            "usage_receipt",
        }
        return {key: value for key, value in task.items() if key not in hidden}
