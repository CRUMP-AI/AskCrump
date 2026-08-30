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


def test_latest_result_prioritizes_one_click_private_continuity_before_feedback_and_referral():
    ui = (ROOT / "public" / "ui-functions.js").read_text(encoding="utf-8")
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "projects.py").read_text(encoding="utf-8")

    assert "Start a Project" in ui
    assert r"Keep in \u201c${target.displayName}\u201d" in ui
    assert ui.index("syncOutcomeProjectAction(projectButton)") < ui.index("Or help someone else:")
    assert "group.append(continuityPrompt, projectButton, prompt, ...buttons)" in ui
    assert "group.replaceChildren(continuityPrompt, projectButton, status)" in ui
    assert "Open the Project containing this conversation" in ui
    direct_action = ui[
        ui.index("const continuityPrompt"):
        ui.index("const renderThanks")
    ]
    assert "keepConversation" in direct_action
    assert "OutcomeFeedbackSubmitted" not in direct_action
    assert "projectTarget: () => currentProjectTarget()" in product
    assert "keepConversation: options => keepConversation(options)" in product
    assert "Object.prototype.hasOwnProperty.call(options, 'projectId')" in product
    assert "const targetProjectId" in product
    assert "keepConversation({projectId: projectButton.dataset.projectId || null})" in ui
    assert "await window.syncChatsToServer?.()" in product
    assert 'body: {chatId}' in product
    assert '@router.post("/{project_id}/chats")' in route
    assert 'event_key="first-durable-project"' in route
    assert 'artifact_type="project"' in route


def test_project_save_timeout_fixture_uses_real_product_code_without_credentials():
    fixture = (ROOT / "tests" / "fixtures" / "project-save-stall.html").read_text(
        encoding="utf-8"
    )
    product = (ROOT / "public" / "crump-product-5.3.js").read_text(encoding="utf-8")

    assert '<script src="/public/ui-functions.js?v=project-save-fixture-4"></script>' in fixture
    assert '<script src="/public/crump-product-5.3.js?v=project-save-fixture-3"></script>' in fixture
    assert "fixtureSuccessfulSave" in fixture
    assert "Project save request completed." in fixture
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


def test_project_target_disclosure_fixture_covers_selected_and_new_destinations():
    fixture = (ROOT / "tests" / "fixtures" / "project-target-disclosure.html").read_text(
        encoding="utf-8"
    )

    assert '<script src="/public/ui-functions.js?v=project-target-disclosure-2"></script>' in fixture
    assert '<script src="/public/crump-product-5.3.js?v=project-target-disclosure-2"></script>' in fixture
    assert "Q3 Finance Forecast" in fixture
    assert "Website launch checklist" in fixture
    assert "await wait(120)" in fixture
    assert "fixtureUsesStoredProject" in fixture
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
