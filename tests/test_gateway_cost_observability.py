from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260917234000_ai_gateway_cost_observability.sql"


def test_gateway_cost_migration_is_content_free_and_service_role_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    lowered = sql.lower()

    assert "create table if not exists public.ai_gateway_cost_receipts" in lowered
    assert "enable row level security" in lowered
    assert "revoke all on table public.ai_gateway_cost_receipts from public, anon, authenticated, service_role" in lowered
    for function in (
        "claim_ai_gateway_cost_receipt",
        "settle_ai_gateway_cost_receipt",
        "ai_gateway_provider_cost_aggregate",
    ):
        assert f"create or replace function public.{function}" in lowered
        assert f"grant execute on function public.{function}" in lowered
    for forbidden_column in (
        "user_id uuid",
        "email text",
        "prompt text",
        "response text",
        "filename text",
        "raw_url text",
        "request_body json",
        "credential text",
    ):
        assert forbidden_column not in lowered


def test_gateway_cost_aggregate_is_half_open_and_fails_closed():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "r.created_at >= p_since" in sql
    assert "r.created_at < p_until" in sql
    assert "status <> 'attempted' and usage_receipt_complete" in sql
    assert "status <> 'attempted' and cost_receipt_complete" in sql
    assert "case when usage_complete then input_tokens else null end" in sql
    assert "case when cost_complete then gross_cost else null end" in sql
    assert "case when cost_complete then 0::numeric else null end" in sql
    assert "count(*) filter (where status <> 'completed')" in sql
    assert "count(*) filter (where status = 'rate_limited')" in sql
    assert "count(*) filter (where status = 'budget_rejected')" in sql
    assert "percentile_cont(0.95)" in sql


def test_gateway_cost_capture_covers_every_current_central_purpose():
    ai = (ROOT / "backend" / "ai_service.py").read_text(encoding="utf-8")
    intelligence = (ROOT / "backend" / "intelligence_service.py").read_text(encoding="utf-8")
    runtime = (ROOT / "backend" / "runtime.py").read_text(encoding="utf-8")

    assert "receipt_id = await self._claim_gateway_receipt(context)" in ai
    assert "await self._settle_gateway_receipt(" in ai
    assert "purpose='chat'" in ai
    assert "purpose='check-in'" in ai
    assert 'purpose="creation-router"' in intelligence
    assert 'purpose="answer-verifier"' in intelligence
    assert 'purpose="planner"' in intelligence
    assert "ai = AIService(settings, db)" in runtime


def test_gateway_cost_receipt_has_no_customer_identifier_payload():
    ai = (ROOT / "backend" / "ai_service.py").read_text(encoding="utf-8")
    claim_start = ai.index("async def _claim_gateway_receipt")
    settle_start = ai.index("async def _settle_gateway_receipt")
    claim_source = ai[claim_start:settle_start]

    for prohibited in (
        "p_user_id",
        "p_email",
        "p_prompt",
        "p_response",
        "p_filename",
        "p_url",
        "p_request_body",
        "p_credential",
    ):
        assert prohibited not in claim_source
