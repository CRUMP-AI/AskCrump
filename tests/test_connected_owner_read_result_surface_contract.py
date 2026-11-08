from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20261108062000_connected_owner_read_result_surface.sql"
SURFACE = ROOT / "backend" / "connected_app_read_surface.py"
ROUTE = ROOT / "backend" / "routes" / "connected_apps.py"
UI = ROOT / "public" / "connected-apps-ui.js"
MESSAGES = ROOT / "public" / "ui-functions.js"
CSS = ROOT / "public" / "connected-apps-ui.css"
POSTGRES_TEST = ROOT / "tests" / "postgres" / "test_connected_owner_read_result_surface.sql"


def test_owner_result_migration_is_exact_content_free_and_service_role_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "192b3c7abb884d47736df936c1820bc9" in sql
    assert "f03f8f3204e5623fd950ad1ffb9fd430" in sql
    assert "__TARGET_FINGERPRINT__" not in sql
    assert "connected_app_open_read_result_v1" in sql
    assert "security definer\nset search_path = ''" in sql
    assert "language plpgsql\nvolatile" in sql
    assert "perform connected_app_private.owner_lock_v1(p_owner_id)" in sql
    assert "result.owner_id = p_owner_id" in sql
    assert "result.result_payload_id = p_result_payload_id" in sql
    assert "payload_row.expires_at > payload_row.created_at + interval '7 days'" in sql
    assert "grant execute on function public.connected_app_open_read_result_v1(uuid,uuid)\n  to service_role" in sql
    for role in ("public", "anon", "authenticated"):
        assert re.search(
            rf"revoke all on function public\.connected_app_open_read_result_v1\(uuid,uuid\)\s+from {role}",
            sql,
        )
    returned = sql[sql.index("return pg_catalog.jsonb_build_object(") : sql.index("end;\n$fn$")]
    for forbidden in (
        "payload_ciphertext",
        "payload_nonce",
        "wrapped_key_ciphertext",
        "wrapped_key_nonce",
        "body_text",
        "subject",
        "description",
    ):
        assert forbidden not in returned
    assert "using errcode = '55000'" in sql
    assert POSTGRES_TEST.exists()


def test_application_surface_opens_only_exact_server_custody_binding() -> None:
    source = SURFACE.read_text(encoding="utf-8")
    assert '"connected_app_open_read_result_v1"' in source
    assert "ConnectedReadResultCoordinator.payload_id(self.operation_id)" in source
    assert "await self._results.replay(" in source
    assert "if durable.terminal != index.terminal()" in source
    assert '"trustBoundary": "untrusted_external_data"' in source
    assert "body, body_truncated = _clip(value.body_text, 80_000)" in source
    assert "return \"ConnectedOwnerReadResultService(content='<encrypted>')\"" in source
    assert "logging" not in source


def test_route_is_owner_preconditioned_no_store_and_source_locked() -> None:
    source = ROUTE.read_text(encoding="utf-8")
    assert '@router.get("/results/{result_reference_id}")' in source
    run_owner = source.index("async def _run_owner(")
    release_check = source.index(
        "config.connected_apps_release_candidate_source_released() is not True",
        run_owner,
    )
    environment_check = source.index(
        'or getattr(settings, "connected_apps_enabled", False) is not True',
        release_check,
    )
    owner_check = source.index("owner_id, session_id = await _owner(request)", run_owner)
    activation = source.index("lease = await _acquire_request_activation(", run_owner)
    assert release_check < environment_check < owner_check < activation
    route = source.index('@router.get("/results/{result_reference_id}")')
    assert source.index("result = await _run_owner(request, operation)", route) > route
    assert source.index("read_results = connected_read_result_service", route) > route
    assert "require_expected_owner_header=True" in source
    assert '_NO_STORE = {"Cache-Control": "private, no-store"}' in source
    assert 'result_reference_id=_canonical_uuid(result_reference_id)' in source


def test_chat_result_viewer_is_click_only_text_only_and_owner_scrubbed() -> None:
    ui = UI.read_text(encoding="utf-8")
    messages = MESSAGES.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "createConnectedResultReceipt(message)" in messages
    assert "connected-result-open" in messages
    assert "dataset.connectedResultReference" in messages
    assert "CrumpConnectedAppsUI?.openResult?.(" in messages
    assert "openConnectedResult(resultReferenceId, actionId, opener)" in ui
    assert "request(`/results/${encodeURIComponent(resultReferenceId)}`" in ui
    assert "validateReadResult(data, resultReferenceId, actionId)" in ui
    assert "state.resultController?.abort('owner-boundary')" in ui
    assert "closeResultViewer({restoreFocus: false})" in ui
    assert "event.key !== 'Escape'" in ui
    assert "close.focus()" in ui
    assert "opener.focus()" in ui
    assert ".innerHTML" not in ui
    assert "textContent" in ui
    assert "@media (max-width: 430px)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert ".connected-result-dialog" in css
    assert "min-height: 44px" in css


@pytest.mark.parametrize(
    "asset",
    [ROOT / "public" / "connected-apps-ui.js", ROOT / "public" / "ui-functions.js"],
)
def test_result_surface_javascript_parses(asset: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable")
    subprocess.run(
        [node, "--check", str(asset)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
