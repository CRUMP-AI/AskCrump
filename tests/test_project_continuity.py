from pathlib import Path

import pytest

from backend.project_service import ProjectChatNotFoundError, ProjectService
from backend.routes import projects as projects_routes


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
PROJECT_ID = "00000000-0000-0000-0000-000000000002"
CHAT_ID = "00000000-0000-0000-0000-000000000003"


class ProjectContinuityDB:
    def __init__(self, *, owns_chat: bool = True):
        self.owns_chat = owns_chat
        self.calls = []

    async def select_one(self, table, **kwargs):
        self.calls.append(("select_one", table, kwargs))
        if table == "user_chats":
            if not self.owns_chat:
                return None
            return {"chat_id": CHAT_ID, "title": "Quarterly strategy"}
        if table == "projects":
            return {"id": PROJECT_ID, "user_id": USER_ID, "name": "Quarterly strategy"}
        return None

    async def select(self, table, **kwargs):
        self.calls.append(("select", table, kwargs))
        if table == "project_chats":
            return [{"chat_id": CHAT_ID, "created_at": "2026-08-27T12:00:00Z"}]
        if table == "user_chats":
            return [{
                "chat_id": CHAT_ID,
                "title": "Quarterly strategy",
                "created_at": "2026-08-27T12:00:00Z",
                "updated_at": "2026-08-27T13:00:00Z",
            }]
        return []

    async def insert(self, table, payload):
        self.calls.append(("insert", table, payload))
        return [{**payload, "id": PROJECT_ID}]

    async def upsert(self, table, payload, **kwargs):
        self.calls.append(("upsert", table, payload, kwargs))
        return [payload]

    async def update(self, table, payload, **kwargs):
        self.calls.append(("update", table, payload, kwargs))
        return [payload]

    async def delete(self, table, **kwargs):
        self.calls.append(("delete", table, kwargs))
        return []


class JsonRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_create_from_chat_checks_ownership_and_attaches_the_conversation():
    database = ProjectContinuityDB()
    service = ProjectService(database)

    project = await service.create_from_chat(
        user_id=USER_ID,
        chat_id=CHAT_ID,
        name="Quarterly strategy",
        description="Continued from an Ask Crump conversation.",
    )

    assert project["id"] == PROJECT_ID
    owned_lookup = next(call for call in database.calls if call[:2] == ("select_one", "user_chats"))
    assert owned_lookup[2]["columns"] == "chat_id,title"
    assert owned_lookup[2]["filters"] == {
        "user_id": f"eq.{USER_ID}",
        "chat_id": f"eq.{CHAT_ID}",
        "deleted_at": "is.null",
    }
    mapping = next(call for call in database.calls if call[:2] == ("upsert", "project_chats"))
    assert mapping[2] == {
        "project_id": PROJECT_ID,
        "user_id": USER_ID,
        "chat_id": CHAT_ID,
    }


@pytest.mark.asyncio
async def test_create_from_chat_rejects_unowned_or_unsynced_conversations_before_insert():
    database = ProjectContinuityDB(owns_chat=False)
    service = ProjectService(database)

    with pytest.raises(ProjectChatNotFoundError, match="still syncing"):
        await service.create_from_chat(
            user_id=USER_ID,
            chat_id=CHAT_ID,
            name="Should not exist",
        )

    assert not any(call[:2] == ("insert", "projects") for call in database.calls)


@pytest.mark.asyncio
async def test_project_conversations_are_owner_scoped_and_content_free():
    database = ProjectContinuityDB()
    service = ProjectService(database)

    conversations = await service.list_chats(user_id=USER_ID, project_id=PROJECT_ID)

    assert conversations == [{
        "chatId": CHAT_ID,
        "title": "Quarterly strategy",
        "createdAt": "2026-08-27T12:00:00Z",
        "updatedAt": "2026-08-27T13:00:00Z",
    }]
    mapping_lookup = next(call for call in database.calls if call[:2] == ("select", "project_chats"))
    assert mapping_lookup[2]["columns"] == "chat_id,created_at"
    assert mapping_lookup[2]["filters"] == {
        "project_id": f"eq.{PROJECT_ID}",
        "user_id": f"eq.{USER_ID}",
    }
    chat_lookup = next(call for call in database.calls if call[:2] == ("select", "user_chats"))
    assert chat_lookup[2]["columns"] == "chat_id,title,created_at,updated_at"
    assert "messages" not in chat_lookup[2]["columns"]
    assert chat_lookup[2]["filters"]["user_id"] == f"eq.{USER_ID}"
    assert chat_lookup[2]["filters"]["deleted_at"] == "is.null"


@pytest.mark.asyncio
async def test_empty_project_conversation_mapping_does_not_query_chat_records():
    class EmptyProjectDB(ProjectContinuityDB):
        async def select(self, table, **kwargs):
            self.calls.append(("select", table, kwargs))
            return []

    database = EmptyProjectDB()
    service = ProjectService(database)

    assert await service.list_chats(user_id=USER_ID, project_id=PROJECT_ID) == []
    assert not any(call[:2] == ("select", "user_chats") for call in database.calls)


def test_project_workspace_surfaces_saved_conversations_and_a_private_resume_action():
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "projects.py").read_text(encoding="utf-8")

    assert '@router.get("/{project_id}/chats")' in route
    assert '"conversations": conversations' in route
    assert 'id="crump53ProjectConversationsCard"' in product
    assert "refreshProjectConversations()" in product
    assert "await window.syncChatsFromServer?.()" in product
    assert "window.loadChat(normalized)" in product
    resume = product[product.index("async function resumeProjectConversation"):product.index("async function saveProject")]
    assert "chatId:" not in resume
    assert "title:" not in resume
    assert "source: 'project'" in resume


@pytest.mark.asyncio
async def test_project_route_records_content_free_durable_value_after_attach(monkeypatch):
    analytics = []

    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {
            "user": {
                "id": USER_ID,
                "subscription_tier": "professional",
                "subscription_status": "active",
            }
        })()

    class Projects:
        async def count(self, _user_id):
            return 0

        async def create_from_chat(self, **kwargs):
            assert kwargs["user_id"] == USER_ID
            assert kwargs["chat_id"] == CHAT_ID
            return {"id": PROJECT_ID, "name": kwargs["name"]}

    class Features:
        def project_limit(self, _user):
            return 25

    async def record(_database, **kwargs):
        analytics.append(kwargs)
        return True

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())
    monkeypatch.setattr(projects_routes, "features", Features())
    monkeypatch.setattr(projects_routes, "record_product_event", record)

    result = await projects_routes.create_project(JsonRequest({
        "name": "Quarterly strategy",
        "description": "Continued from an Ask Crump conversation.",
        "chatId": CHAT_ID,
    }))

    assert result["success"] is True
    assert result["conversationSaved"] is True
    assert result["project"] == {"id": PROJECT_ID, "name": "Quarterly strategy"}
    assert len(analytics) == 1
    assert analytics[0]["event_name"] == "AhaReached"
    assert analytics[0]["event_key"] == "first-durable-project"
    assert analytics[0]["artifact_type"] == "project"
    assert set(analytics[0]) == {
        "user_id", "event_name", "event_key", "request", "plan", "artifact_type",
    }


def test_latest_result_prioritizes_one_click_private_continuity_before_feedback_and_referral():
    ui = (ROOT / "public" / "ui-functions.js").read_text(encoding="utf-8")
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "projects.py").read_text(encoding="utf-8")

    assert "Keep in a Project" in ui
    assert ui.index("Keep in a Project") < ui.index("Or help someone else:")
    assert "group.append(continuityPrompt, projectButton, prompt, ...buttons)" in ui
    assert "group.replaceChildren(continuityPrompt, projectButton, status)" in ui
    direct_action = ui[
        ui.index("const continuityPrompt"):
        ui.index("const renderThanks")
    ]
    assert "keepConversation" in direct_action
    assert "OutcomeFeedbackSubmitted" not in direct_action
    assert "keepConversation: () => keepConversation()" in product
    assert "await window.syncChatsToServer?.()" in product
    assert 'body: {chatId}' in product
    assert '@router.post("/{project_id}/chats")' in route
    assert 'event_key="first-durable-project"' in route
    assert 'artifact_type="project"' in route
