from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_start_paths_delegate_customer_refunds_to_atomic_database_settlement():
    route = read("backend/routes/media.py")

    assert "_refund_failed_video_charge" not in route
    assert route.count("consume_video_reservation(") == 2
    assert route.count("_read_bound_video_receipt(") >= 4
    assert "VIDEO_BILLING_RECEIPT_PERSIST_FAILED" not in route


def test_provider_launch_failure_rpc_is_identity_fenced_and_refunds_in_transaction():
    migration = read("migrations/20260924230000_atomic_video_reservation_billing.sql")
    fail_rpc = migration.split(
        "create or replace function public.fail_video_provider_launch",
        1,
    )[1].split("revoke all on function", 1)[0]

    for identity in (
        "p_user_id",
        "p_job_id",
        "p_idempotency_key",
        "p_request_fingerprint",
        "p_launch_token",
    ):
        assert identity in fail_rpc
    assert "public.refund_credit_spend" in fail_rpc
    assert "delete from public.usage_events" in fail_rpc
    assert "billing_refunded" in fail_rpc
    assert "acceptance = 'rejected'" in fail_rpc
    assert "else current_job.estimated_provider_cost_cents" in fail_rpc


def test_failed_job_identity_remains_server_private():
    service = read("backend/video_service.py")
    route = read("backend/routes/media.py")

    assert "mapped.failed_job_id = job_id" in service
    assert '"failedJobId"' not in route
    public_error = route.split("def _video_error", 1)[1].split(
        "def _idempotency_key",
        1,
    )[0]
    assert "failed_job_id" not in public_error
