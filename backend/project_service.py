"""Persistent isolated workspaces for Ask Crump Projects."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .db import SupabaseDB, eq, in_
from .security import normalize_chat_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


class ProjectNotFoundError(RuntimeError):
    pass


class ProjectChatNotFoundError(RuntimeError):
    pass


class ProjectService:
    def __init__(self, db: SupabaseDB) -> None:
        self.db = db

    async def count(self, user_id: str) -> int:
        rows = await self.db.select(
            "projects",
            columns="id",
            filters={"user_id": eq(user_id), "archived_at": "is.null"},
            limit=1000,
        )
        return len(rows)

    async def list(self, user_id: str) -> list[dict[str, Any]]:
        return await self.db.select(
            "projects",
            filters={"user_id": eq(user_id), "archived_at": "is.null"},
            order="updated_at.desc",
            limit=250,
        )

    async def get(self, user_id: str, project_id: str) -> dict[str, Any]:
        try:
            normalized = normalize_chat_id(project_id)
        except Exception as exc:
            raise ProjectNotFoundError("Project not found.") from exc
        row = await self.db.select_one(
            "projects",
            filters={
                "id": eq(normalized),
                "user_id": eq(user_id),
                "archived_at": "is.null",
            },
        )
        if not row:
            raise ProjectNotFoundError("Project not found.")
        return row

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        description: str = "",
        instructions: str = "",
    ) -> dict[str, Any]:
        clean_name = _clean(name, 100)
        if not clean_name:
            raise ValueError("Project name is required.")
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "name": clean_name,
            "description": _clean(description, 1200),
            "instructions": str(instructions or "").strip()[:12000],
            "metadata": {},
            "updated_at": _now(),
        }
        result = await self.db.insert("projects", row)
        return (result or [row])[0]

    async def update(
        self,
        *,
        user_id: str,
        project_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        project = await self.get(user_id, project_id)
        updates: dict[str, Any] = {"updated_at": _now()}
        if "name" in changes:
            name = _clean(changes.get("name"), 100)
            if not name:
                raise ValueError("Project name is required.")
            updates["name"] = name
        if "description" in changes:
            updates["description"] = _clean(changes.get("description"), 1200)
        if "instructions" in changes:
            updates["instructions"] = str(changes.get("instructions") or "").strip()[:12000]
        result = await self.db.update(
            "projects",
            updates,
            filters={"id": eq(project["id"]), "user_id": eq(user_id)},
        )
        return (result or [project])[0]

    async def archive(self, user_id: str, project_id: str) -> None:
        project = await self.get(user_id, project_id)
        await self.db.update(
            "projects",
            {"archived_at": _now(), "updated_at": _now()},
            filters={"id": eq(project["id"]), "user_id": eq(user_id)},
        )

    async def owned_chat(self, *, user_id: str, chat_id: str) -> dict[str, Any]:
        try:
            normalized_chat = normalize_chat_id(chat_id)
        except Exception as exc:
            raise ProjectChatNotFoundError("Conversation not found.") from exc
        row = await self.db.select_one(
            "user_chats",
            columns="chat_id,title",
            filters={
                "user_id": eq(user_id),
                "chat_id": eq(normalized_chat),
                "deleted_at": "is.null",
            },
        )
        if not row:
            raise ProjectChatNotFoundError(
                "That conversation is still syncing. Try again in a moment."
            )
        return row

    async def create_from_chat(
        self,
        *,
        user_id: str,
        chat_id: str,
        name: str = "",
        description: str = "",
        instructions: str = "",
    ) -> dict[str, Any]:
        chat = await self.owned_chat(user_id=user_id, chat_id=chat_id)
        item = await self.create(
            user_id=user_id,
            name=name or str(chat.get("title") or "Continued work"),
            description=description,
            instructions=instructions,
        )
        try:
            await self.attach_chat(
                user_id=user_id,
                project_id=str(item["id"]),
                chat_id=str(chat["chat_id"]),
            )
        except Exception:
            # The Project was created only for this operation. Remove it if the
            # conversation mapping cannot be completed so the user never sees a
            # misleading empty workspace or loses one of their plan slots.
            await self.db.delete(
                "projects",
                filters={"id": eq(item["id"]), "user_id": eq(user_id)},
            )
            raise
        return item

    async def attach_owned_chat(
        self,
        *,
        user_id: str,
        project_id: str,
        chat_id: str,
    ) -> dict[str, Any]:
        chat = await self.owned_chat(user_id=user_id, chat_id=chat_id)
        return await self.attach_chat(
            user_id=user_id,
            project_id=project_id,
            chat_id=str(chat["chat_id"]),
        )

    async def attach_chat(
        self,
        *,
        user_id: str,
        project_id: str,
        chat_id: str,
    ) -> dict[str, Any]:
        project = await self.get(user_id, project_id)
        normalized_chat = normalize_chat_id(chat_id)
        await self.db.upsert(
            "project_chats",
            {
                "project_id": project["id"],
                "user_id": user_id,
                "chat_id": normalized_chat,
            },
            on_conflict="project_id,chat_id",
        )
        await self.db.update(
            "projects",
            {"updated_at": _now()},
            filters={"id": eq(project["id"]), "user_id": eq(user_id)},
        )
        return project

    async def list_chats(
        self,
        *,
        user_id: str,
        project_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return content-free metadata for conversations linked to an owned Project."""
        project = await self.get(user_id, project_id)
        safe_limit = max(1, min(100, int(limit)))
        mappings = await self.db.select(
            "project_chats",
            columns="chat_id,created_at",
            filters={"project_id": eq(project["id"]), "user_id": eq(user_id)},
            order="created_at.desc",
            limit=safe_limit,
        )
        chat_ids = [str(row.get("chat_id") or "").strip() for row in mappings]
        chat_ids = [chat_id for chat_id in chat_ids if chat_id]
        if not chat_ids:
            return []

        rows = await self.db.select(
            "user_chats",
            columns="chat_id,title,created_at,updated_at",
            filters={
                "user_id": eq(user_id),
                "chat_id": in_(chat_ids),
                "deleted_at": "is.null",
            },
            order="updated_at.desc",
            limit=safe_limit,
        )
        return [
            {
                "chatId": str(row.get("chat_id") or ""),
                "title": _clean(row.get("title") or "New conversation", 180) or "New conversation",
                "createdAt": row.get("created_at"),
                "updatedAt": row.get("updated_at"),
            }
            for row in rows
            if row.get("chat_id")
        ]

    async def attach_file(
        self,
        *,
        user_id: str,
        project_id: str,
        file_id: str,
        role: str = "asset",
    ) -> None:
        project = await self.get(user_id, project_id)
        normalized_file = normalize_chat_id(file_id)
        await self.db.upsert(
            "project_files",
            {
                "project_id": project["id"],
                "user_id": user_id,
                "file_id": normalized_file,
                "role": _clean(role, 30) or "asset",
            },
            on_conflict="project_id,file_id",
        )

    async def reference_files(
        self,
        *,
        user_id: str,
        project_id: str,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        project = await self.get(user_id, project_id)
        mappings = await self.db.select(
            "project_files",
            filters={"project_id": eq(project["id"]), "user_id": eq(user_id)},
            order="created_at.desc",
            limit=max(1, min(100, int(limit))),
        )
        output: list[dict[str, Any]] = []
        for mapping in mappings:
            file_id = mapping.get("file_id")
            if not file_id:
                continue
            row = await self.db.select_one(
                "user_files",
                filters={
                    "id": eq(file_id),
                    "user_id": eq(user_id),
                    "status": eq("ready"),
                    "deleted_at": "is.null",
                },
            )
            if not row:
                continue
            item = dict(row)
            item["project_role"] = mapping.get("role") or "asset"
            output.append(item)
        return output
    async def add_context(
        self,
        *,
        user_id: str,
        project_id: str,
        kind: str,
        content: str,
        label: str = "",
    ) -> dict[str, Any]:
        project = await self.get(user_id, project_id)
        text = str(content or "").strip()[:16000]
        if not text:
            raise ValueError("Project context cannot be empty.")
        row = {
            "id": str(uuid4()),
            "project_id": project["id"],
            "user_id": user_id,
            "kind": _clean(kind, 30) or "note",
            "label": _clean(label, 120),
            "content": text,
            "updated_at": _now(),
        }
        result = await self.db.insert("project_context", row)
        return (result or [row])[0]

    async def hydrate_context(self, user_id: str, project_id: str) -> dict[str, Any]:
        project = await self.get(user_id, project_id)
        context_rows = await self.db.select(
            "project_context",
            columns="kind,label,content,updated_at",
            filters={"project_id": eq(project["id"]), "user_id": eq(user_id)},
            order="updated_at.desc",
            limit=40,
        )
        manuscripts = await self.db.select(
            "manuscripts",
            columns="id,title,subtitle,status,updated_at",
            filters={
                "project_id": eq(project["id"]),
                "user_id": eq(user_id),
                "archived_at": "is.null",
            },
            order="updated_at.desc",
            limit=12,
        )
        reference_files = await self.reference_files(
            user_id=user_id,
            project_id=project_id,
            limit=20,
        )
        return {
            "project": {
                "id": project["id"],
                "name": project.get("name"),
                "description": project.get("description"),
                "instructions": project.get("instructions"),
            },
            "canon": context_rows,
            "manuscripts": manuscripts,
            "reference_files": [
                {
                    "id": row.get("id"),
                    "name": row.get("file_name"),
                    "type": row.get("mime_type"),
                    "size": row.get("size_bytes"),
                    "role": row.get("project_role"),
                }
                for row in reference_files
            ],
        }
