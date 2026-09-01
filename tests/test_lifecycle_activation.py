from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as app_module
from backend.lifecycle_service import candidate_sequence, session_hash
from backend.routes import lifecycle as lifecycle_routes


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
MIGRATION = ROOT / "migrations" / "20260830175952_in_product_lifecycle_activation.sql"
CLIENT = TestClient(app_module.app)


def facts(**overrides):
    values = {
        "accountEligible": True,
        "accountAgeSeconds": 0,
        "hasFirstRequest": False,
        "hasActivation": False,
        "hasProject": False,
        "hasArtifact": False,
        "hasAha": False,
        "hasRecentWork": False,
        "latestFeedback": None,
        "acquisitionIntent": None,
    }
    values.update(overrides)
    return values


def keys(values):
    return [value["messageKey"] for value in values]


def test_acceptance_candidate_fixtures_are_content_free_and_ordered():
    a = candidate_sequence(facts(acquisitionIntent="presentation"))
    assert a[0] == {
        "messageKey": "starter-assist",
        "intent": "presentation",
        "surface": "workspace-inline",
    }

    c = candidate_sequence(facts(hasActivation=True))
    assert c[0]["messageKey"] == "continuity-assist"

    d = candidate_sequence(facts(hasActivation=True, hasAha=True, hasProject=True))
    assert "continuity-assist" not in keys(d)

    e = candidate_sequence(facts(hasProject=True), "presentation")
    assert e[0]["messageKey"] == "artifact-assist"
    assert e[0]["intent"] == "presentation"

    f = candidate_sequence(
        facts(hasProject=True, hasArtifact=True, hasAha=True),
        "presentation",
    )
    assert "artifact-assist" not in keys(f)

    g = candidate_sequence(facts(hasAha=True, latestFeedback="useful"))
    assert "referral-ask" in keys(g)

    h = candidate_sequence(
        facts(hasAha=True, hasRecentWork=True, latestFeedback="needs_work")
    )
    assert "referral-ask" not in keys(h)


def test_unknown_intent_is_discarded_instead_of_retained_or_hashed():
    sentinel = "PRIVATE_PROJECT_SENTINEL"
    decision = candidate_sequence(facts(acquisitionIntent=sentinel), sentinel)[0]
    assert decision["messageKey"] == "starter-assist"
    assert decision["intent"] is None
    assert sentinel not in repr(decision)


def test_session_key_is_one_way_and_account_session_scoped():
    client_key = "12345678-1234-4123-8123-123456789abc"
    left = session_hash("auth-session-a", client_key)
    right = session_hash("auth-session-b", client_key)
    assert left != right
    assert len(left) == 64
    assert client_key not in left


class LifecycleDB:
    def __init__(self):
        self.calls = []

    async def rpc(self, name, payload):
        self.calls.append((name, payload))
        if name == "lifecycle_prompt_facts":
            return facts(acquisitionIntent="presentation")
        if name == "claim_lifecycle_prompt":
            if payload["p_active_work"]:
                return {
                    "eligible": False,
                    "suppressionReason": "active-work",
                    "terminal": True,
                }
            return {
                "eligible": True,
                "messageKey": payload["p_message_key"],
                "intent": payload["p_intent"],
                "surface": payload["p_surface"],
                "decisionId": "00000000-0000-4000-8000-000000000001",
            }
        if name == "record_lifecycle_prompt_action":
            return {"recorded": True}
        raise AssertionError(name)


async def fake_authenticate(*_args, **_kwargs):
    return SimpleNamespace(
        user={"id": "00000000-0000-4000-8000-000000000010", "is_verified": True},
        session={"id": "00000000-0000-4000-8000-000000000011"},
        token="token",
    )


def test_decision_endpoint_uses_server_facts_and_suppresses_active_work(monkeypatch):
    database = LifecycleDB()
    monkeypatch.setattr(lifecycle_routes, "db", database)
    monkeypatch.setattr(lifecycle_routes, "authenticate_request", fake_authenticate)
    payload = {
        "sessionId": "12345678-1234-4123-8123-123456789abc",
        "intent": "PRIVATE_PROJECT_SENTINEL",
        "activeWork": True,
        "recoverySurface": False,
        "currentSurface": "ask",
    }
    response = CLIENT.post("/api/lifecycle/decision", json=payload)
    assert response.status_code == 200
    assert response.json() == {"success": True, "eligible": False}
    claim = next(call for call in database.calls if call[0] == "claim_lifecycle_prompt")
    assert claim[1]["p_intent"] == "presentation"
    assert "PRIVATE_PROJECT_SENTINEL" not in repr(database.calls)


def test_action_endpoint_is_idempotency_rpc_backed(monkeypatch):
    database = LifecycleDB()
    monkeypatch.setattr(lifecycle_routes, "db", database)
    monkeypatch.setattr(lifecycle_routes, "authenticate_request", fake_authenticate)
    response = CLIENT.post("/api/lifecycle/actions", json={
        "sessionId": "12345678-1234-4123-8123-123456789abc",
        "decisionId": "00000000-0000-4000-8000-000000000001",
        "action": "shown",
        "currentSurface": "ask",
    })
    assert response.status_code == 200
    assert response.json()["recorded"] is True
    action = next(call for call in database.calls if call[0] == "record_lifecycle_prompt_action")
    assert action[1]["p_action"] == "shown"
    assert len(action[1]["p_session_hash"]) == 64


def test_migration_enforces_caps_holdouts_stale_rechecks_and_private_access():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "holdout_percent smallint not null default 20" in sql
    assert "e.created_at >= now() - interval '7 days'" in sql
    assert ") >= 2 then" in sql
    assert "active_decision_expires_at" in sql
    assert "v_facts := public.lifecycle_prompt_facts" in sql
    assert "unique (decision_id, event_type)" in sql
    assert "enable row level security" in sql
    assert "revoke all on table public.lifecycle_prompt_events from public, anon, authenticated" in sql
    assert "grant execute on function public.claim_lifecycle_prompt" in sql
    assert "product_weekly_lifecycle_export" in sql


def test_lifecycle_storage_schema_has_no_customer_content_fields():
    sql = MIGRATION.read_text(encoding="utf-8")
    state = sql[sql.index("create table if not exists public.lifecycle_prompt_state"):]
    state = state[:state.index(");")]
    events = sql[sql.index("create table if not exists public.lifecycle_prompt_events"):]
    events = events[:events.index(");")]
    for prohibited in (
        "email", "copy", "body", "url", "project_id", "chat_id", "file_id",
        "response", "notification_body",
    ):
        assert f"\n  {prohibited} " not in state.lower()
        assert f"\n  {prohibited} " not in events.lower()


def test_browser_component_uses_only_reviewed_static_copy_and_is_nonblocking():
    manager = (PUBLIC / "lifecycle-manager.js").read_text(encoding="utf-8")
    ui = (PUBLIC / "ui-functions.js").read_text(encoding="utf-8")
    styles = (PUBLIC / "lifecycle.css").read_text(encoding="utf-8")
    runtime = (PUBLIC / "runtime-body-v1.js").read_text(encoding="utf-8")
    worker = (PUBLIC / "sw.js").read_text(encoding="utf-8")
    referral = (PUBLIC / "lifecycle-share.js").read_text(encoding="utf-8")

    required_copy = (
        "Bring one real task",
        "Four details are enough to begin",
        "Keep this work moving",
        "Turn the useful part into something you can keep",
        "Know someone carrying an unfinished project?",
        "Share the workspace, not your private conversation or files.",
    )
    assert all(value in manager for value in required_copy)
    assert "role', 'region'" in manager
    assert "focus({preventScroll: true})" in manager
    assert "activeWork() || recoverySurface()" in manager
    assert "action('shown')" in manager
    assert "action('suppressed', 'active-work')" in manager
    assert "let volatileSessionId = '';" in manager
    assert "if (!volatileSessionId) volatileSessionId = crypto.randomUUID();" in manager
    assert "window.CrumpOutcomeActions.keepLatestInProject()" in manager
    assert "keepLatestInProject: () => keepLatestOutcomeInProject()" in ui
    assert "return performOutcomeProjectAction(projectButton);" in ui
    continuity = manager[manager.index("if (decision.messageKey === 'continuity-assist'"):]
    continuity = continuity[:continuity.index("if (typeof navigation?.open !== 'function')")]
    assert "navigation.open('projects')" not in continuity
    assert "prefers-reduced-motion: reduce" in styles
    assert "/lifecycle-manager.js?v=5.9.76-continuity-action-1" in runtime
    assert "/lifecycle.css?v=5.9.76-lifecycle-activation-1" in runtime
    assert "ask-crump-new-body-v1-r185" in worker
    assert (ROOT / "tests" / "fixtures" / "lifecycle-project-continuity.html").exists()
    assert (ROOT / "scripts" / "verify-lifecycle-project-continuity.cjs").exists()
    assert "eventKey: `response-share:${day}`" in referral
    assert "workspace-referral:" not in referral


def test_terms_consent_does_not_enable_lifecycle_email_or_push():
    source = "\n".join([
        (ROOT / "backend" / "lifecycle_service.py").read_text(encoding="utf-8"),
        (ROOT / "backend" / "routes" / "lifecycle.py").read_text(encoding="utf-8"),
        MIGRATION.read_text(encoding="utf-8"),
        (PUBLIC / "lifecycle-manager.js").read_text(encoding="utf-8"),
    ]).lower()
    assert "send_email" not in source
    assert "email_service" not in source
    assert "push_service" not in source
    assert "/notifications/register" not in source
