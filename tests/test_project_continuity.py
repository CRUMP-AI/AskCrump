import json
from pathlib import Path

import pytest

from backend import sync_service
from backend.db import DatabaseError
from backend.file_service import FileServiceError
from backend.product53_hooks import apply_project_context, attach_generated_outputs
from backend.project_service import ProjectChatNotFoundError, ProjectNotFoundError, ProjectService
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


class ProjectContextBoundary:
    def __init__(self, linked_project=None):
        self.linked_project = linked_project
        self.calls = []

    async def find_for_chat(self, **kwargs):
        self.calls.append(("find_for_chat", kwargs))
        return self.linked_project

    async def hydrate_context(self, user_id, project_id):
        self.calls.append(("hydrate_context", {"user_id": user_id, "project_id": project_id}))
        return {
            "project": {"id": project_id, "name": "Quarterly strategy"},
            "canon": [],
        }

    async def attach_chat(self, **kwargs):
        self.calls.append(("attach_chat", kwargs))

    async def attach_file(self, **kwargs):
        self.calls.append(("attach_file", kwargs))


@pytest.mark.asyncio
async def test_chat_context_recovers_existing_owner_scoped_project_relationship():
    projects = ProjectContextBoundary({"id": PROJECT_ID, "name": "Quarterly strategy"})
    payload = {"message": "Continue where we left off."}

    project_id = await apply_project_context(
        user_id=USER_ID,
        payload=payload,
        chat_id=CHAT_ID,
        file_rows=[],
        projects=projects,
    )

    assert project_id == PROJECT_ID
    assert projects.calls[0] == (
        "find_for_chat",
        {"user_id": USER_ID, "chat_id": CHAT_ID},
    )
    assert any(kind == "hydrate_context" for kind, _ in projects.calls)
    assert any(kind == "attach_chat" for kind, _ in projects.calls)
    assert payload["relevantContext"][0]["source"] == "project_workspace"


@pytest.mark.asyncio
async def test_confirmed_unrelated_chat_skips_project_lookup_and_strips_client_marker():
    projects = ProjectContextBoundary({"id": PROJECT_ID, "name": "Quarterly strategy"})
    payload = {
        "message": "Plan an unrelated dinner.",
        "projectContextChecked": True,
    }

    project_id = await apply_project_context(
        user_id=USER_ID,
        payload=payload,
        chat_id=CHAT_ID,
        file_rows=[],
        projects=projects,
    )

    assert project_id is None
    assert projects.calls == []
    assert "projectContextChecked" not in payload
    assert "relevantContext" not in payload


@pytest.mark.asyncio
async def test_explicit_project_context_wins_without_relationship_lookup():
    projects = ProjectContextBoundary({"id": "not-used"})
    payload = {
        "message": "Use the selected workspace.",
        "projectId": PROJECT_ID,
        "projectContextChecked": True,
    }

    project_id = await apply_project_context(
        user_id=USER_ID,
        payload=payload,
        chat_id=CHAT_ID,
        file_rows=[],
        projects=projects,
    )

    assert project_id == PROJECT_ID
    assert not any(kind == "find_for_chat" for kind, _ in projects.calls)
    assert any(kind == "hydrate_context" for kind, _ in projects.calls)
    assert "projectContextChecked" not in payload


@pytest.mark.asyncio
async def test_generated_output_attachment_returns_truthful_independent_receipts():
    calls = []

    class Projects:
        async def attach_file(self, **kwargs):
            calls.append(kwargs)
            if kwargs["role"] == "generated_image":
                raise DatabaseError("temporary outage")

    receipts = await attach_generated_outputs(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        result={
            "imageFile": {"id": "00000000-0000-0000-0000-000000000091"},
            "artifact": {"id": "00000000-0000-0000-0000-000000000092"},
        },
        projects=Projects(),
    )

    assert receipts == {
        "imageFile": {
            "status": "failed",
            "projectId": PROJECT_ID,
            "role": "generated_image",
            "shouldRetry": True,
            "message": "The file is safe in Files, but its Project link needs a retry.",
        },
        "artifact": {
            "status": "attached",
            "projectId": PROJECT_ID,
            "role": "generated_document",
            "shouldRetry": False,
        },
    }
    assert [call["role"] for call in calls] == ["generated_image", "generated_document"]
    assert all(call["user_id"] == USER_ID and call["project_id"] == PROJECT_ID for call in calls)


@pytest.mark.asyncio
async def test_generated_output_does_not_offer_retry_for_a_missing_project():
    class MissingProject:
        async def attach_file(self, **_kwargs):
            raise ProjectNotFoundError("Project not found.")

    receipts = await attach_generated_outputs(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        result={"artifact": {"id": "00000000-0000-0000-0000-000000000092"}},
        projects=MissingProject(),
    )

    assert receipts == {
        "artifact": {
            "status": "missing",
            "projectId": PROJECT_ID,
            "role": "generated_document",
            "shouldRetry": False,
            "message": "The file is safe in Files, but its original Project is no longer available.",
        }
    }


def test_missing_output_project_can_be_retargeted_instead_of_retrying_the_dead_id():
    ui = (ROOT / "public" / "crump-5.0.js").read_text(encoding="utf-8")

    assert "receipt.status === 'missing'" in ui
    assert "const targetProjectId = receipt?.status === 'failed' ? receipt.projectId : '';" in ui
    assert "Safe in Files · Original Project is no longer available · Choose another Project" in ui
    assert "receipt?.status === 'missing' ? 'Add to another Project'" in ui
    assert "targetProjectId && Number(error?.status) === 404" in ui
    assert "Original Project is no longer available. Choose another Project." in ui


def test_generated_output_project_receipts_survive_sync_with_a_content_free_allowlist():
    message = sync_service.sanitize_message({
        "id": "assistant-1",
        "role": "assistant",
        "content": "Your files are ready.",
        "projectAttachments": {
            "artifact": {
                "status": "attached",
                "projectId": PROJECT_ID,
                "role": "attacker-controlled",
                "shouldRetry": True,
                "message": "attacker-controlled",
                "secret": "must not survive",
            },
            "imageFile": {
                "status": "missing",
                "projectId": PROJECT_ID,
                "role": "attacker-controlled",
                "shouldRetry": True,
                "message": "attacker-controlled",
            },
            "unexpected": {
                "status": "failed",
                "projectId": PROJECT_ID,
                "secret": "must not survive",
            },
        },
    })

    assert message["projectAttachments"] == {
        "artifact": {
            "status": "attached",
            "projectId": PROJECT_ID,
            "role": "generated_document",
            "shouldRetry": False,
        },
        "imageFile": {
            "status": "missing",
            "projectId": PROJECT_ID,
            "role": "generated_image",
            "shouldRetry": False,
            "message": "The file is safe in Files, but its original Project is no longer available.",
        },
    }


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
async def test_create_from_chat_reuses_an_existing_project_after_an_uncertain_response():
    class ExistingProjectDB(ProjectContinuityDB):
        async def select(self, table, **kwargs):
            self.calls.append(("select", table, kwargs))
            if table == "project_chats" and kwargs.get("columns") == "project_id":
                return [{"project_id": PROJECT_ID}]
            if table == "projects":
                return [{"id": PROJECT_ID, "user_id": USER_ID, "name": "Quarterly strategy"}]
            return []

    database = ExistingProjectDB()
    service = ProjectService(database)

    project = await service.create_from_chat(
        user_id=USER_ID,
        chat_id=CHAT_ID,
        name="Duplicate should not be created",
    )

    assert project["id"] == PROJECT_ID
    assert not any(call[:2] == ("insert", "projects") for call in database.calls)
    mapping_lookup = next(
        call for call in database.calls
        if call[:2] == ("select", "project_chats")
        and call[2].get("columns") == "project_id"
    )
    assert mapping_lookup[2]["filters"] == {
        "user_id": f"eq.{USER_ID}",
        "chat_id": f"eq.{CHAT_ID}",
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


@pytest.mark.asyncio
async def test_project_for_chat_route_returns_only_the_owner_scoped_summary(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {"user": {"id": USER_ID}})()

    class Projects:
        async def find_for_chat(self, **kwargs):
            assert kwargs == {"user_id": USER_ID, "chat_id": CHAT_ID}
            return {
                "id": PROJECT_ID,
                "user_id": USER_ID,
                "name": "Quarterly strategy",
                "description": "Private description",
                "instructions": "Private instructions",
            }

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())

    result = await projects_routes.project_for_chat(CHAT_ID, object())

    assert result == {
        "success": True,
        "project": {"id": PROJECT_ID, "name": "Quarterly strategy"},
    }


@pytest.mark.asyncio
async def test_project_for_chat_route_returns_null_without_leaking_missing_chat_state(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {"user": {"id": USER_ID}})()

    class Projects:
        async def find_for_chat(self, **_kwargs):
            raise ProjectChatNotFoundError("Conversation not found.")

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())

    assert await projects_routes.project_for_chat("not-a-chat-id", object()) == {
        "success": True,
        "project": None,
    }


@pytest.mark.asyncio
async def test_project_target_route_returns_only_the_owner_scoped_summary(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {"user": {"id": USER_ID}})()

    class Projects:
        async def get(self, user_id, project_id):
            assert user_id == USER_ID
            assert project_id == PROJECT_ID
            return {
                "id": PROJECT_ID,
                "user_id": USER_ID,
                "name": "Quarterly strategy",
                "description": "Private description",
                "instructions": "Private instructions",
            }

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())

    result = await projects_routes.project_target(PROJECT_ID, object())

    assert result == {
        "success": True,
        "project": {"id": PROJECT_ID, "name": "Quarterly strategy"},
    }


@pytest.mark.asyncio
async def test_project_file_list_reports_database_outage_instead_of_false_empty_success(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {"user": {"id": USER_ID}})()

    class Projects:
        async def get(self, user_id, project_id):
            assert (user_id, project_id) == (USER_ID, PROJECT_ID)
            return {"id": PROJECT_ID}

    class Database:
        async def select(self, table, **kwargs):
            assert table == "project_files"
            assert kwargs["filters"]["user_id"] == f"eq.{USER_ID}"
            return [{"file_id": "00000000-0000-0000-0000-000000000099", "role": "generated_document"}]

    class Files:
        async def get_owned(self, **_kwargs):
            raise DatabaseError("temporary outage")

        def public_file(self, _row):
            raise AssertionError("An unavailable row must not be rendered.")

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())
    monkeypatch.setattr(projects_routes, "db", Database())
    monkeypatch.setattr(projects_routes, "files", Files())

    response = await projects_routes.project_files(PROJECT_ID, object())
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload == {
        "success": False,
        "error": "Projects are temporarily unavailable. Try again.",
        "code": "PROJECTS_UNAVAILABLE",
        "shouldRetry": True,
    }


@pytest.mark.asyncio
async def test_project_file_list_skips_only_a_genuinely_missing_owned_file(monkeypatch):
    missing_id = "00000000-0000-0000-0000-000000000098"
    ready_id = "00000000-0000-0000-0000-000000000099"

    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {"user": {"id": USER_ID}})()

    class Projects:
        async def get(self, _user_id, _project_id):
            return {"id": PROJECT_ID}

    class Database:
        async def select(self, *_args, **_kwargs):
            return [
                {"file_id": missing_id, "role": "generated_document"},
                {"file_id": ready_id, "role": "reference"},
            ]

    class Files:
        async def get_owned(self, *, user_id, file_id):
            assert user_id == USER_ID
            if file_id == missing_id:
                raise FileServiceError("File not found.", 404, "FILE_NOT_FOUND")
            return {"id": ready_id, "file_name": "launch-plan.docx"}

        def public_file(self, row):
            return {"id": row["id"], "name": row["file_name"]}

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())
    monkeypatch.setattr(projects_routes, "db", Database())
    monkeypatch.setattr(projects_routes, "files", Files())

    result = await projects_routes.project_files(PROJECT_ID, object())

    assert result == {
        "success": True,
        "files": [{"id": ready_id, "name": "launch-plan.docx", "projectRole": "reference"}],
    }


@pytest.mark.asyncio
async def test_project_file_attach_preserves_missing_and_retryable_failure_semantics(monkeypatch):
    file_id = "00000000-0000-0000-0000-000000000099"

    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {"user": {"id": USER_ID}})()

    class Projects:
        async def get(self, _user_id, _project_id):
            return {"id": PROJECT_ID}

        async def attach_file(self, **_kwargs):
            raise AssertionError("A missing or unavailable file must not be attached.")

    class MissingFile:
        async def get_owned(self, **_kwargs):
            raise FileServiceError("File not found.", 404, "FILE_NOT_FOUND")

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())
    monkeypatch.setattr(projects_routes, "files", MissingFile())

    missing = await projects_routes.attach_project_file(
        PROJECT_ID,
        JsonRequest({"fileId": file_id, "role": "generated_document"}),
    )

    assert missing.status_code == 404
    assert json.loads(missing.body)["code"] == "FILE_NOT_FOUND"

    class UnavailableFile:
        async def get_owned(self, **_kwargs):
            raise DatabaseError("temporary outage")

    monkeypatch.setattr(projects_routes, "files", UnavailableFile())
    unavailable = await projects_routes.attach_project_file(
        PROJECT_ID,
        JsonRequest({"fileId": file_id, "role": "generated_document"}),
    )
    unavailable_payload = json.loads(unavailable.body)

    assert unavailable.status_code == 503
    assert unavailable_payload["code"] == "PROJECTS_UNAVAILABLE"
    assert unavailable_payload["shouldRetry"] is True


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
    assert "window.CrumpNavigation5930.open('ask')" in resume
    assert "byId('userInput')?.focus({preventScroll: true})" in resume
    assert "chatId:" not in resume
    assert "title:" not in resume
    assert "source: 'project'" in resume


def test_project_rows_open_a_real_project_workspace_and_scoped_new_chat():
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    styles = (ROOT / "public" / "crump-product-5.3.css").read_text(encoding="utf-8")
    fixture = (ROOT / "tests" / "fixtures" / "project-open-navigation.html").read_text(
        encoding="utf-8"
    )

    assert 'id="crump53ProjectBack"' in product
    assert 'id="crump53ProjectWorkspaceName"' in product
    assert 'id="crump53StartProjectChat"' in product
    assert 'id="crump53ProjectSettings"' in product
    assert product.index('id="crump53StartProjectChat"') < product.index('id="crump53ProjectSettings"')
    assert "if (settings) settings.open = false" in product
    assert "if (settings) settings.open = true" in product
    assert 'aria-label="Open Project ${escapeHtml(item.name)}"' in product
    assert 'href="${escapeHtml(projectRouteHref(item.id))}"' in product
    assert "const PROJECT_ROUTE_PARAM = 'project'" in product
    assert "new URL(window.location.pathname, window.location.origin)" in product
    assert "window.history[replace ? 'replaceState' : 'pushState']" in product
    assert "window.addEventListener('popstate'" in product
    assert "wireProjectLinks(list)" in product
    assert "link.addEventListener('click'" in product
    assert "link.setAttribute('aria-busy', 'true')" in product
    assert "if (!opened) window.location.assign(link.href)" in product
    assert "return true" in product
    assert "String(item.id || '') === normalizedProjectId" in product
    assert "setProjectView('detail', {focus: false})" in product
    assert "renderActiveProjectWorkspace({open: focus})" in product
    assert "setProjectView('detail'" in product
    assert "window.CrumpBodyV1.command('new')" in product
    assert "Message Crump in ${name}" in product
    assert "document.querySelector('.v1-workspace-context')" in product
    assert '[data-crump53-panel="projects"].is-project-open .crump53-project-index-card' in styles
    assert '[data-crump53-panel="projects"].is-project-open > .crump53-grid' in styles
    assert '.crump53-project-hero-actions' in styles
    assert '.crump53-project-settings summary' in styles
    assert 'id="fixtureProjectView"' in fixture
    assert 'id="fixtureProjectRoute"' in fixture
    assert "const holdFixture = fixtureParams.get('hold') === '1'" in fixture
    assert "new URLSearchParams(location.search).get('project')" in fixture
    assert "sheet?.dataset.projectView" in fixture
    assert 'aria-label="Started Project chat"' in fixture
    assert 'aria-label="Project file requests"' in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert "/public/crump-product-5.3.1.js?v=project-home-fixture-8" in fixture
    assert "Launch brief.pdf" in fixture
    assert "fixture-user" in fixture
    assert "password" not in fixture.lower()


def test_top_level_studios_clear_project_only_navigation_state():
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    verifier = (ROOT / "scripts" / "verify-studio-section-isolation.cjs").read_text(
        encoding="utf-8"
    )

    configure = product[
        product.index("function configureStudioSection") : product.index("function openStudio")
    ]
    assert "if (section !== 'projects')" in configure
    assert "state.projectView = 'index';" in configure
    assert "projectBack.hidden = true;" in configure
    assert "projectsPanel?.classList.remove('is-project-open');" in configure
    assert "sheet.dataset.projectView = 'index';" in configure
    assert "writeProjectRoute('', {replace: true});" in configure
    for section in ("video", "library", "manuscripts"):
        assert f"{{name: '{section}'" in verifier
    assert "projectBackHidden: true" in verifier
    assert "projectPanelOpen: false" in verifier
    assert "routeProject: ''" in verifier


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


@pytest.mark.asyncio
async def test_project_route_retry_reuses_the_saved_project_even_at_the_plan_limit(monkeypatch):
    analytics = []

    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {
            "user": {
                "id": USER_ID,
                "subscription_tier": "free",
                "subscription_status": "active",
            }
        })()

    class Projects:
        async def count(self, _user_id):
            return 3

        async def find_for_chat(self, **kwargs):
            assert kwargs == {"user_id": USER_ID, "chat_id": CHAT_ID}
            return {"id": PROJECT_ID, "name": "Quarterly strategy"}

        async def create_from_chat(self, **_kwargs):
            raise AssertionError("An uncertain-response retry must not create a duplicate Project.")

    class Features:
        def project_limit(self, _user):
            return 3

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

    assert result == {
        "success": True,
        "project": {"id": PROJECT_ID, "name": "Quarterly strategy"},
        "limit": 3,
        "conversationSaved": True,
    }
    assert len(analytics) == 1
    assert analytics[0]["event_name"] == "AhaReached"
    assert analytics[0]["event_key"] == "first-durable-project"


@pytest.mark.asyncio
async def test_result_action_new_project_records_server_completed_save(monkeypatch):
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
        "continuitySource": "result_action",
    }))

    assert result["success"] is True
    assert [event["event_name"] for event in analytics] == [
        "AhaReached",
        "ProjectSaveCompleted",
    ]
    assert analytics[1]["event_key"] == "result-action-save"
    assert analytics[1]["source"] == "new_project"
    assert "chat_id" not in analytics[1]
    assert "project_id" not in analytics[1]


@pytest.mark.asyncio
async def test_result_action_existing_project_records_server_completed_save(monkeypatch):
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
        async def attach_owned_chat(self, **kwargs):
            assert kwargs == {
                "user_id": USER_ID,
                "project_id": PROJECT_ID,
                "chat_id": CHAT_ID,
            }
            return {"id": PROJECT_ID, "name": "Quarterly strategy"}

    async def record(_database, **kwargs):
        analytics.append(kwargs)
        return True

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(projects_routes, "projects", Projects())
    monkeypatch.setattr(projects_routes, "record_product_event", record)

    result = await projects_routes.attach_project_chat(PROJECT_ID, JsonRequest({
        "chatId": CHAT_ID,
        "continuitySource": "result_action",
    }))

    assert result["success"] is True
    assert [event["event_name"] for event in analytics] == [
        "AhaReached",
        "ProjectSaveCompleted",
    ]
    assert analytics[1]["event_key"] == "result-action-save"
    assert analytics[1]["source"] == "existing_project"


@pytest.mark.asyncio
async def test_project_routes_reject_an_invented_save_source(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return type("Auth", (), {"user": {"id": USER_ID}})()

    monkeypatch.setattr(projects_routes, "authenticate_request", authenticate)
    response = await projects_routes.create_project(JsonRequest({
        "chatId": CHAT_ID,
        "continuitySource": "private-project-name",
    }))

    assert response.status_code == 400
    assert json.loads(response.body) == {
        "success": False,
        "error": "Invalid Project save source.",
        "code": "INVALID_PROJECT_SAVE_SOURCE",
    }


def test_latest_result_prioritizes_one_click_private_continuity_before_feedback_and_referral():
    ui = (ROOT / "public" / "ui-functions.js").read_text(encoding="utf-8")
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "projects.py").read_text(encoding="utf-8")

    assert "Start a Project" in ui
    assert r"Keep in \u201c${target.displayName}\u201d" in ui
    assert ui.index("syncOutcomeProjectAction(projectButton)") < ui.index("Or help someone else:")
    assert "group.append(continuityPrompt, projectButton, prompt, ...buttons)" in ui
    assert "group.replaceChildren(continuityPrompt, projectButton, status)" in ui
    assert r'Open Project \u201c${projectName}\u201d containing this conversation' in ui
    assert "showSavedOutcomeProject(projectButton, result.project)" in ui
    assert "'ProjectSaveIntentReached'" in ui
    assert "eventKey: 'project-save-intent'" in ui
    assert "source: targetProjectId ? 'existing_project' : 'new_project'" in ui
    assert "projectButton.textContent = 'Saving…';" in ui
    assert "Saving this conversation privately…" in ui
    assert "Couldn’t save yet. Your conversation is still here." in ui
    assert 'Saved privately to "${projectName}".' in ui
    assert "projectButton.dataset.chatId = String(window.currentChatId" in ui
    assert "hydrateOutcomeProjectAction(projectButton)" in ui
    assert "window.addEventListener?.('crump:project-service-ready'" in ui
    assert "if (await openProject(projectId)) return" in ui
    direct_action = ui[
        ui.index("const continuityPrompt"):
        ui.index("const renderThanks")
    ]
    assert "keepConversation" in direct_action
    assert "OutcomeFeedbackSubmitted" not in direct_action
    assert "projectTarget: () => currentProjectTarget()" in product
    assert "projectForConversation: chatId => projectForConversation(chatId)" in product
    assert "resolveOutcomeProject: chatId => resolveOutcomeProject(chatId)" in product
    assert "/api/projects/target/" in product
    assert "conversationProjectCache" in product
    assert "/api/projects/for-chat/" in product
    assert "rememberConversationProject(chatId, data.project)" in product
    assert "window.dispatchEvent(new Event('crump:project-service-ready'))" in product
    assert "keepConversation: options => keepConversation(options)" in product
    assert "openProject: projectId => openProject(projectId)" in product
    assert "return selectProject(normalizedProjectId)" in product
    assert "Object.prototype.hasOwnProperty.call(options, 'projectId')" in product
    assert "const targetProjectId" in product
    assert "projectId: targetProjectId || null" in ui
    assert "continuitySource: 'result_action'" in ui
    assert "await window.syncChatsToServer?.()" in product
    assert "...(continuitySource ? {continuitySource} : {})" in product
    assert '@router.post("/{project_id}/chats")' in route
    assert '@router.get("/for-chat/{chat_id}")' in route
    assert '"project": project' in route
    assert 'event_key="first-durable-project"' in route
    assert 'artifact_type="project"' in route
    assert 'event_name="ProjectSaveCompleted"' in route
    assert 'event_key="result-action-save"' in route

    relationship_guard = ui[
        ui.index("async function hydrateOutcomeProjectAction"):
        ui.index("function syncOutcomeProjectActions")
    ]
    assert "button.dataset.projectLookup = 'pending';" in relationship_guard
    assert "button.disabled = true;" in relationship_guard
    assert "button.setAttribute('aria-busy', 'true');" in relationship_guard
    assert "button.textContent = 'Checking Project…';" in relationship_guard
    assert relationship_guard.index("button.disabled = true;") < relationship_guard.index("await resolver(chatId)")
    assert "if (button.dataset.saved !== 'true') syncOutcomeProjectAction(button);" in relationship_guard
    assert "button.disabled = wasDisabled;" in relationship_guard


def test_project_chat_context_is_explicit_visible_and_relationship_scoped():
    app = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    styles = (ROOT / "public" / "crump-product-5.3.css").read_text(encoding="utf-8")
    fixture = (ROOT / "tests" / "fixtures" / "project-chat-context-boundary.html").read_text(
        encoding="utf-8"
    )

    assert "function announceConversationOpened" in app
    assert app.count("announceConversationOpened(") >= 7
    assert "crump:conversation-opened" in app
    injection = product[
        product.index("function injectProjectIntoChatRequests"):
        product.index("function injectNavigation")
    ]
    assert "state.chatProject" in injection
    assert "state.activeProject?.id" not in injection
    assert "projectContextChecked = true" in injection
    assert "await projectForConversation(chatId)" in injection
    assert "chatProjectOptOuts" in injection
    assert "Stop using ${escapeHtml(projectName)} context in this conversation" in product
    assert "Context is applied to this conversation." in product
    assert "crump53-mobile-chat-project" in styles
    assert "--ac-dock: 146px" in styles
    assert "project-chat-context-boundary-1" in fixture
    assert "/api/projects/for-chat/" in fixture
    assert "/api/chat" in fixture
    assert "fixtureChatRequests" in fixture
    assert "window.loadChat = chatId => window.fixtureOpenConversation(chatId)" in fixture
    assert "window.fixtureDestinations.push(destination)" in fixture
    verifier = (ROOT / "scripts" / "verify-project-chat-context-boundary.cjs").read_text(
        encoding="utf-8"
    )
    assert "activeElementId: document.activeElement?.id || ''" in verifier
    assert "assert.equal(resumed.activeElementId, 'userInput'" in verifier
    assert (ROOT / "scripts" / "verify-project-chat-context-boundary.cjs").exists()


def test_generated_artifact_can_join_a_project_with_its_source_conversation():
    ui = (ROOT / "public" / "crump-5.0.js").read_text(encoding="utf-8")
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "chat.py").read_text(encoding="utf-8")
    fixture = (ROOT / "tests" / "fixtures" / "project-target-disclosure.html").read_text(
        encoding="utf-8"
    )

    assert "data-artifact-project" in ui
    assert "Add to Project" in ui
    assert "Open Project" in ui
    assert "Retry Project save" in ui
    assert "Safe in Files · Project link needs retry" in ui
    assert "kind: 'imageFile', role: 'generated_image'" in ui
    assert "window.CrumpProduct53?.keepArtifact" in ui
    assert "result['projectAttachments'] = project_attachments" in route
    assert "assistant_message['projectAttachments'] = result['projectAttachments']" in route
    assert "async function keepArtifact(file, options = {})" in product
    assert "notify: false" in product
    assert "refresh: false" in product
    assert "const role = options.role === 'generated_image' ? 'generated_image' : 'generated_document'" in product
    assert "body: {fileId, role}" in product
    assert "keepArtifact: (file, options) => keepArtifact(file, options)" in product
    assert "/public/crump-5.0.js?v=artifact-project-handoff-1" in fixture
    assert "fixtureFileRequest" in fixture
    assert "body.role" in fixture


def test_project_save_timeout_fixture_uses_real_product_code_without_credentials():
    fixture = (ROOT / "tests" / "fixtures" / "project-save-stall.html").read_text(
        encoding="utf-8"
    )
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")

    assert '<script src="/public/ui-functions.js?v=project-save-fixture-5"></script>' in fixture
    assert '<script src="/public/crump-product-5.3.js?v=project-save-fixture-4"></script>' in fixture
    assert "fixtureSuccessfulSave" in fixture
    assert "Project save request completed." in fixture
    assert "window.__fixture.savedProject" in fixture
    assert "window.__fixture.analytics.push({eventName, values})" in fixture
    assert "window.__fixture.projectBodies.push" in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert "unhandledrejection" in fixture
    assert "Project save request stalled." in fixture
    assert "options.signal?.addEventListener('abort'" in fixture
    assert "fixture-user" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture
    assert "const PROJECT_SAVE_TIMEOUT_MS = 15_000" in product
    assert "timeoutMs: PROJECT_SAVE_TIMEOUT_MS" in product
    assert "void refreshProjects()" in product
    verifier = (ROOT / "scripts" / "verify-project-save-activation.cjs").read_text(encoding="utf-8")
    assert "project-save-intent" in verifier
    assert "continuitySource, 'result_action'" in verifier
    assert "Saving this conversation privately" in verifier
    assert "Couldn’t save yet" in verifier
    assert "Saved privately" in verifier


def test_project_target_disclosure_fixture_covers_selected_and_new_destinations():
    fixture = (ROOT / "tests" / "fixtures" / "project-target-disclosure.html").read_text(
        encoding="utf-8"
    )

    assert '<script src="/public/ui-functions.js?v=persisted-project-target-1"></script>' in fixture
    assert '<script src="/public/crump-product-5.3.js?v=persisted-project-target-1"></script>' in fixture
    assert "Q3 Finance Forecast" in fixture
    assert "Website launch checklist" in fixture
    assert "await wait(120)" in fixture
    assert "fixtureUsesStoredProject" in fixture
    assert "fixtureConversationAlreadySaved" in fixture
    assert "fixtureSlowLookup" in fixture
    assert "if (fixtureSlowLookup) await wait(1600);" in fixture
    assert "/api/projects/for-chat/" in fixture
    assert "/api/projects/target/" in fixture
    assert "Project relationship lookups" in fixture
    assert "Remembered project lookups" in fixture
    assert "fixtureStoredLookup === 'stale'" in fixture
    assert "fixtureStoredLookup === 'error'" in fixture
    assert "Opened project" in fixture
    assert "context: {canon: []}" in fixture
    assert "conversations: []" in fixture
    assert "window.__fixture.requests.push" in fixture
    assert 'aria-label="Browser errors"' in fixture
    assert "unhandledrejection" in fixture
    assert "fixture-user" in fixture
    assert "password" not in fixture.lower()


def test_project_return_timeout_fixture_uses_real_project_runtime_without_credentials():
    fixture = (ROOT / "tests" / "fixtures" / "project-return-stall.html").read_text(
        encoding="utf-8"
    )
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")

    assert '<script src="/public/crump-product-5.3.js?v=project-return-fixture-3"></script>' in fixture
    assert "Loading saved conversations" in product
    assert "fixtureSuccessfulReturn" in fixture
    assert "fixtureStall" in fixture
    assert "stalledResponse" in fixture
    assert "stalledBodyResponse" in fixture
    assert "fixture response body was aborted" in fixture
    assert "options.signal?.addEventListener('abort'" in fixture
    assert "fixture-user" in fixture
    assert "password" not in fixture.lower()
    assert "askcrump.com" not in fixture
    assert "const PROJECT_READ_TIMEOUT_MS = 15_000" in product
    assert "Retry loading Projects" in product
    assert "Retry loading saved conversations" in product
    assert "Retry loading Project notes" in product
    assert "if (controller?.signal.aborted || callerSignal?.aborted) throw error" in product
    context = product[
        product.index("async function refreshProjectContext"):
        product.index("async function addProjectContext")
    ]
    assert context.count("if (state.activeProject?.id !== projectId) return") == 2
