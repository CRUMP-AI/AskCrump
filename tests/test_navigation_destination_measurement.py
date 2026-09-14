from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260914210257_navigation_destination_selection.sql"


def normalized_migration() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_navigation_event_contract_is_exact_and_content_free() -> None:
    sql = normalized_migration()

    assert "'navigationdestinationselected'" in sql
    assert "product_events_navigation_destination_check" in sql
    assert (
        "source in ( 'ask', 'chats', 'projects', 'create', 'video', 'library', "
        "'you', 'intelligence', 'code' )"
    ) in sql
    assert "^navigation-destination-selected:(ask|chats|projects|create|video|library|you|intelligence|code):" in sql
    for field in ("plan", "artifact_type", "placement", "campaign", "creative", "intent"):
        assert f"and {field} is null" in sql
    return_contract = sql.split("returns table (", 1)[1].split(") language plpgsql", 1)[0]
    for forbidden in ("prompt", "response", "filename", "email", "user_id", "project_id", "referrer"):
        assert forbidden not in return_contract


def test_navigation_snapshot_has_fixed_rows_and_private_execution() -> None:
    sql = normalized_migration()
    signature = (
        "public.product_navigation_discovery_snapshot( timestamptz, timestamptz, text, boolean )"
    )

    assert "security invoker" in sql
    assert "set search_path = ''" in sql
    assert f"revoke all on function {signature} from public, anon, authenticated" in sql
    assert f"grant execute on function {signature} to service_role" in sql
    assert "join public.users as u on u.id = e.user_id" in sql
    assert "u.registration_environment = p_environment" in sql
    assert "coalesce(u.internal_tier, '') = ''" in sql
    assert "e.environment = p_environment" in sql
    assert "e.event_name in ('workspaceopened', 'navigationdestinationselected')" in sql
    assert "count(distinct s.user_id)::bigint" in sql
    assert "count(s.user_id)::bigint" in sql
    for destination in (
        "ask",
        "chats",
        "projects",
        "create",
        "video",
        "library",
        "you",
        "intelligence",
        "code",
    ):
        assert f"'{destination}'::text" in sql


def test_runtime_wires_every_measured_destination_after_visible_open() -> None:
    navigation = (ROOT / "public" / "crump-navigation-5.9.30.js").read_text(encoding="utf-8")
    body = (ROOT / "public" / "crump-v1-body.js").read_text(encoding="utf-8")
    intelligence = (ROOT / "public" / "crump-4.4.js").read_text(encoding="utf-8")

    for destination in ("ask", "projects", "create", "video", "library", "you", "code"):
        assert f"recordDestinationSelection('{destination}')" in navigation
    assert "source: 'chats'" in body
    assert "if (!wasOpen) recordConversationLibrarySelection()" in body
    assert "if (wasCollapsed) recordConversationLibrarySelection()" in body
    assert "source: 'intelligence'" in intelligence
    assert "NavigationDestinationSelected" in navigation
    assert "NavigationDestinationSelected" in body
    assert "NavigationDestinationSelected" in intelligence
