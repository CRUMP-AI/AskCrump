from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = (
    ROOT / "migrations" / "20260924230000_atomic_video_reservation_billing.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
NORMALIZED = " ".join(SQL.lower().split())


def split_top_level_sql_statements(sql: str) -> list[str]:
    """Split migration statements while respecting strings and dollar bodies."""
    statements: list[str] = []
    current: list[str] = []
    index = 0
    single_quoted = False
    double_quoted = False
    line_comment = False
    block_comment_depth = 0
    dollar_tag: str | None = None

    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            current.append(char)
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment_depth:
            current.append(char)
            if char == "/" and following == "*":
                current.append(following)
                block_comment_depth += 1
                index += 2
                continue
            if char == "*" and following == "/":
                current.append(following)
                block_comment_depth -= 1
                index += 2
                continue
            index += 1
            continue
        if dollar_tag is not None:
            if sql.startswith(dollar_tag, index):
                current.append(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
            else:
                current.append(char)
                index += 1
            continue
        if single_quoted:
            current.append(char)
            if char == "'":
                if following == "'":
                    current.append(following)
                    index += 2
                    continue
                single_quoted = False
            index += 1
            continue
        if double_quoted:
            current.append(char)
            if char == '"':
                if following == '"':
                    current.append(following)
                    index += 2
                    continue
                double_quoted = False
            index += 1
            continue

        if char == "-" and following == "-":
            current.extend((char, following))
            line_comment = True
            index += 2
            continue
        if char == "/" and following == "*":
            current.extend((char, following))
            block_comment_depth = 1
            index += 2
            continue
        if char == "'":
            current.append(char)
            single_quoted = True
            index += 1
            continue
        if char == '"':
            current.append(char)
            double_quoted = True
            index += 1
            continue
        if char == "$":
            closing = sql.find("$", index + 1)
            if closing != -1:
                possible_tag = sql[index : closing + 1]
                tag_name = possible_tag[1:-1]
                if not tag_name or tag_name.replace("_", "a").isalnum():
                    current.append(possible_tag)
                    dollar_tag = possible_tag
                    index = closing + 1
                    continue
        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    assert not single_quoted
    assert not double_quoted
    assert not line_comment
    assert block_comment_depth == 0
    assert dollar_tag is None
    assert not "".join(current).strip()
    return statements


def function_sql(name: str, next_name: str | None = None) -> str:
    start = SQL.lower().index(f"create or replace function public.{name}(")
    if next_name:
        end = SQL.lower().index(
            f"create or replace function public.{next_name}(", start + 1
        )
    else:
        end = SQL.lower().index("revoke all on function", start + 1)
    return SQL[start:end].lower()


def test_video_state_is_durable_and_explicitly_constrained():
    for column in (
        "request_fingerprint text",
        "video_phase text not null default 'legacy'",
        "lease_token uuid",
        "lease_expires_at timestamptz",
        "finalization_started_at timestamptz",
        "provider_started_at timestamptz",
        "sweep_retry_after timestamptz not null default '-infinity'::timestamptz",
    ):
        assert column in NORMALIZED

    for phase in (
        "legacy",
        "reserved_unbilled",
        "ready_to_launch",
        "launching",
        "processing",
        "finalizing",
        "ready",
        "failed",
    ):
        assert f"'{phase}'" in NORMALIZED

    assert "request_fingerprint ~ '^[0-9a-f]{64}$'" in NORMALIZED
    assert "on public.media_jobs(user_id, video_phase, lease_expires_at)" in NORMALIZED


def test_capacity_and_lease_queries_have_partial_supporting_indexes():
    expected_indexes = (
        "create index if not exists media_jobs_video_lease_sweep_idx "
        "on public.media_jobs(lease_expires_at, id) where kind = 'video' "
        "and lease_expires_at is not null and video_phase in ( "
        "'reserved_unbilled', 'ready_to_launch', 'launching', 'finalizing' )",
        "create index if not exists media_jobs_video_stale_processing_idx "
        "on public.media_jobs(updated_at, id) include (user_id) where kind = 'video' "
        "and status = 'processing' and video_phase = 'processing'",
        "create index if not exists media_jobs_video_processing_deadline_idx "
        "on public.media_jobs(provider_started_at, sweep_retry_after, id) "
        "include (user_id) where kind = 'video' and status = 'processing' "
        "and video_phase = 'processing'",
        "create index if not exists media_jobs_video_finalization_deadline_idx "
        "on public.media_jobs(finalization_started_at, lease_expires_at, id) "
        "include (user_id) where kind = 'video' and status = 'processing' "
        "and video_phase = 'finalizing'",
        "create index if not exists media_jobs_video_compat_refund_sweep_idx "
        "on public.media_jobs(sweep_retry_after, updated_at, id) include (user_id) "
        "where kind = 'video' and status = 'failed' and video_phase = 'failed' "
        "and not billing_refunded and billing_receipt <> '{}'::jsonb and "
        "coalesce(metadata ->> 'compatibilityorigin', '') = 'pre-atomic'",
        "create index if not exists media_jobs_video_global_daily_budget_idx "
        "on public.media_jobs(created_at) include (estimated_provider_cost_cents, "
        "video_phase, lease_expires_at) where kind = 'video'",
        "create index if not exists media_jobs_video_user_daily_budget_idx "
        "on public.media_jobs(user_id, created_at) include "
        "(estimated_provider_cost_cents, video_phase, lease_expires_at) "
        "where kind = 'video'",
        "create index if not exists media_jobs_video_runway_monthly_budget_idx "
        "on public.media_jobs(created_at) include (estimated_provider_cost_cents, "
        "video_phase, lease_expires_at) where kind = 'video' and provider = 'runway'",
    )
    for index_sql in expected_indexes:
        assert index_sql in NORMALIZED


def test_every_video_rpc_is_invoker_only_with_exact_service_role_signature():
    assert "security definer" not in NORMALIZED
    assert NORMALIZED.count("security invoker") == 12

    compatibility_signature = "public.normalize_pre_atomic_video_job()"
    assert (
        f"revoke all on function {compatibility_signature} "
        "from public, anon, authenticated" in NORMALIZED
    )
    assert (
        f"grant execute on function {compatibility_signature} to service_role"
        in NORMALIZED
    )

    signatures = (
        "public.authorize_video_reservation_capacity( uuid, uuid, text, text, "
        "text, integer, integer, integer, integer, boolean )",
        "public.consume_video_reservation( uuid, uuid, text, text, text, text, "
        "text, text, integer, integer, text, text, text, integer, integer, jsonb )",
        "public.claim_video_provider_launch( uuid, uuid, text, text, text, integer, "
        "boolean )",
        "public.release_video_reservation( uuid, uuid, text, text, text, text )",
        "public.complete_video_provider_launch( uuid, uuid, text, text, text, text )",
        "public.fail_video_provider_launch( uuid, uuid, text, text, text, text, text, "
        "boolean, text )",
        "public.claim_video_finalization( uuid, uuid, text, text, text, integer, "
        "text, boolean )",
        "public.complete_video_finalization( uuid, uuid, text, text, text, uuid, "
        "text, timestamptz, bigint, jsonb )",
        "public.fail_video_finalization( uuid, uuid, text, text, text, text, text, "
        "boolean )",
        "public.claim_video_reconciliation_batch( integer, integer, integer )",
        "public.sweep_expired_video_leases(integer, uuid, uuid)",
    )
    for signature in signatures:
        assert (
            f"revoke all on function {signature} from public, anon, authenticated"
            in NORMALIZED
        )
        assert f"grant execute on function {signature} to service_role" in NORMALIZED


def test_request_identity_and_leases_are_not_authorized_from_metadata():
    assert NORMALIZED.count(
        "job_row.idempotency_key is distinct from normalized_key"
    ) == 9
    assert NORMALIZED.count(
        "job_row.request_fingerprint is distinct from normalized_fingerprint"
    ) == 9
    assert NORMALIZED.count("'request_conflict'::text") == 9

    for forbidden in (
        "metadata ->> 'videophase'",
        "metadata ->> 'reservationtoken'",
        "metadata ->> 'reservationexpiresat'",
        "metadata ->> 'launchtoken'",
        "metadata ->> 'launchexpiresat'",
        "metadata ->> 'launchreadyexpiresat'",
        "metadata ->> 'billingpending'",
    ):
        assert forbidden not in SQL.lower()

    for name, next_name in (
        ("consume_video_reservation", "claim_video_provider_launch"),
        ("claim_video_provider_launch", "release_video_reservation"),
        ("release_video_reservation", "complete_video_provider_launch"),
        ("complete_video_provider_launch", "fail_video_provider_launch"),
        ("fail_video_provider_launch", None),
    ):
        body = function_sql(name, next_name)
        assert "job_row.video_phase" in body
        assert "request_fingerprint" in body
        assert "idempotency_key" in body

    assert "job_row.lease_token is distinct from reservation_token" in function_sql(
        "consume_video_reservation", "claim_video_provider_launch"
    )
    assert "job_row.lease_token is distinct from launch_token" in function_sql(
        "complete_video_provider_launch", "fail_video_provider_launch"
    )
    assert "job_row.lease_token is distinct from launch_token" in function_sql(
        "fail_video_provider_launch"
    )


def test_private_rpcs_accept_only_the_bounded_historical_key_window():
    validation = "if normalized_key = '' or length(normalized_key) > 160 then"
    assert NORMALIZED.count(validation) == 9
    assert (
        "if normalized_key = '' or length(normalized_key) > 120 then"
        not in NORMALIZED
    )


def test_billing_and_customer_first_failure_settlement_are_atomic_and_terminal():
    consume = function_sql(
        "consume_video_reservation", "claim_video_provider_launch"
    )
    claim = function_sql(
        "claim_video_provider_launch", "release_video_reservation"
    )
    failure = function_sql("fail_video_provider_launch")

    assert "public.consume_usage_event(" in consume
    assert "public.spend_credits_confirmed(" in consume
    assert "set billing_receipt = bound_receipt" in consume
    assert "video_phase = 'ready_to_launch'" in consume
    settlement = "public.sweep_expired_video_leases(500, p_user_id, null)"
    assert settlement in consume
    assert "settlement_outcome is distinct from 'completed'" in consume
    assert "coalesce(settlement_errors, 0) > 0" in consume
    assert "return query select 'settlement_pending'::text" in consume
    assert "video owner billing settlement is pending" not in consume
    assert consume.index(settlement) < consume.index("public.consume_usage_event(")
    assert consume.index(settlement) < consume.index("public.spend_credits_confirmed(")

    assert "'ready_expired'::text" in claim
    assert "'ambiguous_failed'::text" in claim
    assert "public.refund_credit_spend(" in claim
    assert "delete from public.usage_events" in claim
    assert claim.count("video launch credit receipt is invalid") == 2
    assert claim.count("video launch usage receipt is invalid") == 2
    assert claim.count("video launch payment source is invalid") == 2
    assert claim.count("payment_source in ('internal', 'subscription')") == 2
    assert "event_id is null" in claim
    assert "video_phase = 'failed'" in claim
    assert "providerfailurecode', 'video_provider_launch_unconfirmed'" in claim
    assert "set video_phase = 'ready_to_launch'" not in claim

    assert "if coalesce(p_refund_eligible" not in failure
    assert "payment_source = 'credits'" in failure
    assert "payment_source = 'included'" in failure
    assert "failed video launch credit receipt is invalid" in failure
    assert "failed video launch usage receipt is invalid" in failure
    assert "failed video launch payment source is invalid" in failure
    assert "payment_source in ('internal', 'subscription')" in failure
    assert "and event_id is null" in failure
    assert "when acceptance = 'rejected' then 0" in failure
    assert "else current_job.estimated_provider_cost_cents" in failure
    assert "video_phase = 'failed'" in failure
    assert "lease_token = null" in failure
    assert "lease_expires_at = null" in failure


def test_same_launch_token_replays_a_committed_active_claim():
    claim = function_sql(
        "claim_video_provider_launch", "release_video_reservation"
    )
    active_launch = claim[
        claim.index("if phase = 'launching'"):
        claim.index("event_id :=", claim.index("if phase = 'launching'"))
    ]
    assert "job_row.lease_token = launch_token" in active_launch
    assert "select 'claimed'::text" in active_launch
    assert "select 'launch_in_progress'::text" in active_launch


def test_expired_lease_sweep_isolates_poison_rows_and_validates_receipts():
    sweep = function_sql("sweep_expired_video_leases")
    assert "errors integer" in sweep
    assert "exception when others" in sweep
    assert "error_count := error_count + 1" in sweep
    assert "sweepneedsreview', true" in sweep
    assert "now() + interval '24 hours'" in sweep
    assert "expired video credit receipt is invalid" in sweep
    assert "expired video usage receipt is invalid" in sweep
    assert "invalid_datetime_format or datetime_field_overflow" in sweep
    assert "error_count" in sweep[sweep.rindex("return query select"):]


def test_pre_atomic_rows_are_backfilled_and_future_old_app_writes_are_fenced():
    compatibility = function_sql(
        "normalize_pre_atomic_video_job", "consume_video_reservation"
    )

    assert "returns trigger" in compatibility
    assert "security invoker" in compatibility
    assert "new.video_phase = 'legacy'" in compatibility
    assert "compatibilityorigin', '') = 'pre-atomic'" in compatibility
    assert "'compatibilityorigin', 'pre-atomic'" in compatibility
    assert "'compatibilityrequestidentity', 'database-row-uuid-v1'" in compatibility
    assert "'pre-atomic-video:' || gen_random_uuid()::text" in compatibility
    assert "length(trim(new.idempotency_key)) > 160" in compatibility
    assert "tg_op = 'insert'" in compatibility
    assert "length(trim(new.idempotency_key)) > 120" in compatibility
    assert "is_rolling_deploy_insert := tg_op = 'insert'" in compatibility
    assert "new.video_phase = 'legacy'" in compatibility
    assert "new.request_fingerprint is null" in compatibility
    assert "new.lease_token is null" in compatibility
    assert "new.lease_expires_at is null" in compatibility
    assert "and not is_rolling_deploy_insert" in compatibility
    assert "candidate.user_id = new.user_id" in compatibility
    assert "candidate.id <> new.id" in compatibility
    assert "candidate.idempotency_key = compatibility_key" in compatibility
    assert "compatibility_key_attempts >= 8" in compatibility
    assert "'pre-atomic-video:' || new.id::text" not in compatibility
    assert "new.idempotency_key is distinct from old.idempotency_key" in compatibility
    assert "old.video_phase in ('ready', 'failed')" in compatibility
    assert "old.status = old.video_phase" in compatibility
    assert "new := old" in compatibility
    assert "new.billing_refunded := true" in compatibility
    assert "legacy_ack_valid" in compatibility
    assert "legacy_ack_payment_source = 'credits'" in compatibility
    assert "legacy_ack_payment_source = 'included'" in compatibility
    assert "legacy_ack_payment_source in ('internal', 'subscription')" in compatibility
    assert "legacy_ack_event_id is null" in compatibility
    assert "'sweepreviewreason', 'invalid-legacy-refund-ack'" in compatibility
    terminal_fence = compatibility[
        compatibility.index("-- a delayed response from any old application"):
        compatibility.index("is_compatibility_row :=")
    ]
    assert "new.status is distinct from old.status" not in terminal_fence
    assert "new.metadata := old.metadata || jsonb_build_object(" in terminal_fence

    fingerprint_start = compatibility.rindex("new.request_fingerprint :=")
    fingerprint_end = compatibility.index("new.metadata :=", fingerprint_start)
    fingerprint_expression = compatibility[fingerprint_start:fingerprint_end]
    assert fingerprint_expression.count("new.id::text") == 2
    assert "md5('askcrump-pre-atomic-a:'" in fingerprint_expression
    assert "md5('askcrump-pre-atomic-b:'" in fingerprint_expression
    for customer_content in (
        "prompt",
        "metadata",
        "provider_asset_reference",
        "file_id",
        "project_id",
        "reference",
        "url",
    ):
        assert customer_content not in fingerprint_expression

    assert (
        "create trigger media_jobs_pre_atomic_video_compatibility "
        "before insert or update on public.media_jobs for each row execute function "
        "public.normalize_pre_atomic_video_job()" in NORMALIZED
    )
    assert (
        "update public.media_jobs set video_phase = video_phase "
        "where kind = 'video' and video_phase = 'legacy'" in NORMALIZED
    )
    assert "check (kind <> 'video' or video_phase <> 'legacy')" in NORMALIZED
    identity_start = NORMALIZED.index(
        "add constraint media_jobs_video_request_identity_check"
    )
    identity_end = NORMALIZED.index(
        "drop constraint if exists media_jobs_video_phase_consistency_check",
        identity_start,
    )
    identity = NORMALIZED[identity_start:identity_end]
    assert "kind <> 'video' or (" in identity
    assert "request_fingerprint is not null" in identity
    assert "request_fingerprint ~ '^[0-9a-f]{64}$'" in identity
    assert "idempotency_key is not null" in identity
    assert "trim(idempotency_key) <> ''" in identity
    assert "length(trim(idempotency_key)) <= 120" in identity
    assert "length(trim(idempotency_key)) <= 160" in identity
    assert "metadata ->> 'compatibilityorigin'" in identity
    assert "metadata ->> 'compatibilityrequestidentity'" in identity
    assert "'database-row-uuid-v1'" in identity
    assert "md5('askcrump-pre-atomic-a:' || id::text)" in identity
    assert "md5('askcrump-pre-atomic-b:' || id::text)" in identity
    consistency_start = NORMALIZED.index(
        "add constraint media_jobs_video_phase_consistency_check"
    )
    consistency_end = NORMALIZED.index("comment on function", consistency_start)
    consistency = NORMALIZED[consistency_start:consistency_end]
    assert "check ( kind <> 'video' or (" in consistency
    assert "provider_job_id is not null" in consistency
    assert "trim(provider_job_id) <> ''" in consistency
    assert "provider_job_id not like 'pending:%'" in consistency


def test_pre_atomic_transition_matrix_has_grace_promotion_and_no_resurrection():
    compatibility = function_sql(
        "normalize_pre_atomic_video_job", "consume_video_reservation"
    )

    # Billed pending rows may already have reached the provider, so they are
    # fenced as acceptance-unknown for a full rolling-deploy grace period.
    assert "new.billing_receipt <> '{}'::jsonb" in compatibility
    assert "new.video_phase := 'launching'" in compatibility
    assert "now() + interval '15 minutes'" in compatibility

    # An old unbilled placeholder is safe to retry only after its short
    # reservation lease is reconciled and deleted.
    assert "new.video_phase := 'reserved_unbilled'" in compatibility
    assert "now() + interval '5 minutes'" in compatibility

    # A real provider id arriving from the old process wins the row lock and
    # promotes the job without a second launch.
    assert "not has_pending_provider_id" in compatibility
    assert "new.status in ('queued', 'processing')" in compatibility
    assert "new.status := 'processing'" in compatibility
    assert "new.video_phase := 'processing'" in compatibility

    # Once reconciliation reaches either terminal state, stale progress,
    # success, failure, or metadata-only writes from the old process are no-ops.
    terminal_guard = compatibility[
        compatibility.index("-- a delayed response from any old application") :
        compatibility.index("is_compatibility_row :=")
    ]
    assert "old.video_phase in ('ready', 'failed')" in terminal_guard
    assert "old.status = old.video_phase" in terminal_guard
    assert "new.provider_job_id is distinct from old.provider_job_id" not in terminal_guard
    assert "new.metadata := old.metadata || jsonb_build_object(" in terminal_guard
    assert "return old" in terminal_guard

    # Explicit modern RPC phase changes keep their own lease fencing values.
    assert "is_explicit_phase_transition" in compatibility
    assert "new.video_phase is distinct from old.video_phase" in compatibility
    assert "preserve" in compatibility


def test_capacity_authorization_serializes_limits_and_releases_only_the_caller():
    capacity = function_sql(
        "authorize_video_reservation_capacity", "consume_video_reservation"
    )
    consume = function_sql(
        "consume_video_reservation", "claim_video_provider_launch"
    )

    assert "pg_advisory_xact_lock" in capacity
    assert "askcrump-video-capacity-v1" in capacity
    assert "active_total > p_max_active_jobs" in capacity
    assert "candidate.provider_started_at > now() - interval '24 hours'" in capacity
    assert "candidate.finalization_started_at > now() - interval '1 hour'" in capacity
    assert "global_total > p_global_daily_budget_cents" in capacity
    assert "user_total > p_user_daily_budget_cents" in capacity
    assert "runway_total > p_runway_monthly_budget_cents" in capacity
    assert "job_row.provider = 'runway'" in capacity
    assert "current_job.id = p_job_id" in capacity
    assert "current_job.user_id = p_user_id" in capacity
    assert "current_job.idempotency_key = normalized_key" in capacity
    assert "current_job.request_fingerprint = normalized_fingerprint" in capacity
    assert "current_job.lease_token = reservation_token" in capacity
    assert "current_job.billing_receipt = '{}'::jsonb" in capacity
    assert "'capacityauthorized', true" in capacity
    assert "'capacitypolicy', 'serialized-v1'" in capacity
    assert "capacity_not_authorized" in consume
    assert "metadata ->> 'capacityauthorized'" in consume
    assert "'processing', 'finalizing', 'ready'" in consume


def test_terminal_finalization_is_token_fenced_idempotent_and_refund_aware():
    claim = function_sql(
        "claim_video_finalization", "complete_video_finalization"
    )
    complete = function_sql(
        "complete_video_finalization", "fail_video_finalization"
    )
    failure = function_sql(
        "fail_video_finalization", "claim_video_reconciliation_batch"
    )

    assert "video_phase = 'finalizing'" in claim
    assert "job_row.lease_token = finalization_token" in claim
    assert "job_row.lease_expires_at > now()" in claim
    assert "current_job.lease_expires_at <= now()" in claim
    assert "'finalization_conflict'::text" in claim
    assert "is distinct from terminal_outcome" in claim
    assert "current_job.video_phase = 'finalizing'" in claim
    assert "job_row.finalization_started_at <= now() - interval '1 hour'" in claim
    assert "return query select 'expired'::text" in claim
    assert "finalization_started_at = coalesce(" in claim
    assert "current_job.finalization_started_at" in claim
    assert "lease_expires_at = least(" in claim
    assert "current_job.finalization_started_at, now() ) + interval '1 hour'" in " ".join(claim.split())
    assert "and coalesce(p_refund_eligible, true)" in claim
    assert "else coalesce(p_refund_eligible, true)" in claim

    assert "p_file_id is distinct from p_job_id" in complete
    assert "insert into public.user_files" in complete
    assert "p_user_id::text || '/' || p_file_id::text || '.mp4'" in complete
    assert "'generated_video'" in complete
    assert "coalesce(p_file_metadata, '{}'::jsonb)" in complete
    assert "where user_files.user_id = excluded.user_id" in complete
    assert "and user_files.kind = 'generated_video'" in complete
    assert complete.index("insert into public.user_files") < complete.index(
        "update public.media_jobs as current_job"
    )
    assert "current_job.lease_token = finalization_token" in complete
    assert "job_row.finalization_started_at <= now() - interval '1 hour'" in complete
    assert "job_row.lease_expires_at <= now()" in complete
    assert "return query select 'expired'::text" in complete
    assert "video_phase = 'ready'" in complete
    assert "finalization_started_at = null" in complete

    assert "refund_allowed" in failure
    assert "and coalesce(p_refund_eligible, true)" in failure
    assert "public.refund_credit_spend(" in failure
    assert "delete from public.usage_events" in failure
    assert "failed video finalization credit receipt is invalid" in failure
    assert "failed video finalization usage receipt is invalid" in failure
    assert "failed video finalization payment source is invalid" in failure
    assert "payment_source in ('internal', 'subscription')" in failure
    assert "and event_id is null" in failure
    assert "current_job.lease_token = finalization_token" in failure
    assert "job_row.finalization_started_at <= now() - interval '1 hour'" in failure
    assert "job_row.lease_expires_at <= now()" in failure
    assert "return query select 'expired'::text" in failure
    assert "'refundeligible', false" in failure
    assert "finalization_started_at = null" in failure


def test_expired_lease_sweep_is_bounded_private_and_never_relaunches_provider():
    sweep = function_sql("sweep_expired_video_leases")

    assert "p_limit > 500" in sweep
    assert "p_user_id is null or candidate.user_id = p_user_id" in sweep
    assert "p_job_id is null or candidate.id = p_job_id" in sweep
    assert "p_job_id is not null and p_user_id is null" in sweep
    assert "or (p_user_id is not null and p_job_id is null)" in sweep
    assert "pg_try_advisory_xact_lock" in sweep
    global_lock = sweep.index("askcrump-video-lease-sweep-v1")
    owner_lock = sweep.index("askcrump-video-owner-billing-v1:")
    assert sweep.rfind("if p_user_id is null", 0, global_lock) >= 0
    assert owner_lock > global_lock
    assert "for update skip locked" in sweep
    assert "limit p_limit" in sweep
    assert "current_job.billing_receipt = '{}'::jsonb" in sweep
    assert "from public.user_files" in sweep
    assert "candidate_file.id = job_row.id" in sweep
    assert "public.refund_credit_spend(" in sweep
    assert "delete from public.usage_events" in sweep
    assert "video_phase = 'failed'" in sweep
    assert "candidate.finalization_started_at <= now() - interval '1 hour'" in sweep
    assert "current_job.finalization_started_at <= now() - interval '1 hour'" in sweep
    assert "candidate.provider_started_at <= now() - interval '24 hours'" in sweep
    assert "current_job.provider_started_at <= now() - interval '24 hours'" in sweep
    assert "candidate.sweep_retry_after <= now()" in sweep
    assert "current_job.sweep_retry_after <= now()" in sweep
    assert "current_job.lease_token is not distinct from job_row.lease_token" in sweep
    assert "when 'processing' then 'video_provider_processing_expired'" in sweep
    assert "when 'failed' then coalesce(" in sweep
    assert "'video_compatibility_refund_recovered'" in sweep
    assert "jsonb_typeof(job_row.metadata -> 'refundeligible') <> 'boolean'" in sweep
    assert "candidate.metadata -> 'refundeligible' = 'true'::jsonb" in sweep
    assert "(job_row.metadata ->> 'refundeligible')::boolean" in sweep
    assert "compatibility_recovery_settled" in sweep
    assert "payment_source in ('internal', 'subscription')" in sweep
    assert "expired video payment source is invalid" in sweep
    assert "candidate.sweep_retry_after asc" in sweep
    assert "candidate.updated_at" in sweep
    assert "if p_user_id is null and not pg_try_advisory_xact_lock(" in sweep
    assert "from public.media_jobs as remaining" in sweep
    assert "return query select 'pending'::text" in sweep
    retry_override = "or (p_user_id is not null and p_job_id is null)"
    assert sweep.count(retry_override) >= 3
    assert "candidate.video_phase = 'failed'" in sweep
    assert "candidate.metadata ->> 'compatibilityorigin'" in sweep
    assert "sweep_retry_after = now() + interval '24 hours'" in sweep
    assert "set lease_expires_at = now() + interval '24 hours'" not in sweep
    assert "provider.start" not in sweep
    assert "claim_video_provider_launch" not in sweep


def test_finalization_deadline_column_is_required_and_indexed():
    assert "add column if not exists finalization_started_at timestamptz" in NORMALIZED
    phase_constraint = NORMALIZED.split(
        "add constraint media_jobs_video_phase_consistency_check", 1
    )[1].split("comment on function public.normalize_pre_atomic_video_job", 1)[0]
    launching = phase_constraint.split("video_phase = 'launching'", 1)[1].split(
        "video_phase = 'processing'", 1
    )[0]
    finalizing = phase_constraint.split("video_phase = 'finalizing'", 1)[1].split(
        "video_phase = 'ready'", 1
    )[0]
    assert "finalization_started_at" not in launching
    assert "and finalization_started_at is not null" in finalizing
    assert "media_jobs_video_finalization_deadline_idx" in NORMALIZED
    assert "on public.media_jobs(finalization_started_at, lease_expires_at, id)" in NORMALIZED


def test_processing_deadline_is_immutable_bounded_and_refund_settled():
    phase_constraint = NORMALIZED.split(
        "add constraint media_jobs_video_phase_consistency_check", 1
    )[1].split("comment on function public.normalize_pre_atomic_video_job", 1)[0]
    processing = phase_constraint.split("video_phase = 'processing'", 1)[1].split(
        "video_phase = 'finalizing'", 1
    )[0]
    finalizing = phase_constraint.split("video_phase = 'finalizing'", 1)[1].split(
        "video_phase = 'ready'", 1
    )[0]
    launch = function_sql(
        "complete_video_provider_launch", "fail_video_provider_launch"
    )
    claim = function_sql(
        "claim_video_finalization", "complete_video_finalization"
    )

    assert "and provider_started_at is not null" in processing
    assert "and provider_started_at is not null" in finalizing
    assert "provider_started_at = coalesce(current_job.provider_started_at, now())" in launch
    assert "job_row.provider_started_at <= now() - interval '24 hours'" in claim
    assert "return query select 'expired'::text" in claim


def test_reconciliation_batch_claim_is_atomic_monotonic_and_horizon_bounded():
    claim = function_sql(
        "claim_video_reconciliation_batch", "sweep_expired_video_leases"
    )

    assert "p_limit > 25" in claim
    assert "for update skip locked" in claim
    assert "limit p_limit" in claim
    assert "candidate.sweep_retry_after <= now()" in claim
    assert "candidate.provider_started_at > now() - interval '24 hours'" in claim
    assert "candidate.finalization_started_at > now() - interval '1 hour'" in claim
    assert "greatest( current_job.sweep_retry_after" in " ".join(claim.split())
    assert "least(" in claim
    assert "now() + make_interval(secs => p_backoff_seconds)" in claim
    assert "current_job.provider_started_at + interval '24 hours'" in claim
    assert "current_job.finalization_started_at + interval '1 hour'" in claim
    assert "order by candidate.sweep_retry_after asc" in " ".join(claim.split())
    assert "case when candidate.video_phase = 'finalizing' then 0 else 1 end" not in claim


def test_compatibility_start_time_uses_creation_for_backfill_and_is_immutable():
    trigger = function_sql(
        "normalize_pre_atomic_video_job", "authorize_video_reservation_capacity"
    )

    assert "old.provider_started_at is not null" in trigger
    assert "new.provider_started_at := old.provider_started_at" in trigger
    assert "old.video_phase = 'legacy'" in trigger
    assert "new.provider_started_at := coalesce(new.created_at, now())" in trigger
    assert "new.provider_started_at := now()" in trigger


def test_all_atomic_terminal_rows_reject_stale_old_application_writes():
    trigger = function_sql(
        "normalize_pre_atomic_video_job", "authorize_video_reservation_capacity"
    )
    guard = trigger[
        trigger.index("-- a delayed response from any old application") :
        trigger.index("is_compatibility_row :=")
    ]

    assert "old.video_phase in ('ready', 'failed')" in guard
    assert "old.status = old.video_phase" in guard
    assert guard.index("old.video_phase in ('ready', 'failed')") < guard.index(
        "compatibilityorigin"
    )
    assert "new := old" in guard
    assert "return old" in guard
    assert "requested_sweep_retry_after := new.sweep_retry_after" in guard
    assert "greatest( old.sweep_retry_after, requested_sweep_retry_after )" in " ".join(
        guard.split()
    )


def test_finalizing_retry_backoff_is_an_allowed_control_write():
    trigger = function_sql(
        "normalize_pre_atomic_video_job", "authorize_video_reservation_capacity"
    )
    guard = trigger.split(
        "if tg_op = 'update' and old.video_phase = 'finalizing' then", 1
    )[1].split("-- old application updates can replace metadata wholesale", 1)[0]

    assert "new.sweep_retry_after is distinct from old.sweep_retry_after" in guard


def test_compatibility_and_release_writes_share_the_owner_billing_lock():
    trigger = function_sql(
        "normalize_pre_atomic_video_job", "authorize_video_reservation_capacity"
    )
    release = function_sql(
        "release_video_reservation", "complete_video_provider_launch"
    )

    owner_lock = "askcrump-video-owner-billing-v1:"
    assert owner_lock in trigger
    assert owner_lock in release
    assert trigger.index(owner_lock) < trigger.index("is_compatibility_row :=")
    assert release.index(owner_lock) < release.index("video-billing:")


def test_modern_video_rpcs_never_wait_after_taking_the_owner_lock():
    owner_lock = "askcrump-video-owner-billing-v1:"
    functions = (
        ("claim_video_provider_launch", "release_video_reservation"),
        ("release_video_reservation", "complete_video_provider_launch"),
        ("complete_video_provider_launch", "fail_video_provider_launch"),
        ("fail_video_provider_launch", "claim_video_finalization"),
        ("claim_video_finalization", "complete_video_finalization"),
        ("complete_video_finalization", "fail_video_finalization"),
        ("fail_video_finalization", "claim_video_reconciliation_batch"),
    )

    for name, next_name in functions:
        body = function_sql(name, next_name)
        owner = body.index(owner_lock)
        secondary = body.index("pg_try_advisory_xact_lock", owner)
        row_lock = body.index("for update skip locked", secondary)
        busy = body.index("return query select 'busy'::text", secondary)
        assert owner < secondary < row_lock
        assert secondary < busy < row_lock
        assert "if exists ( select 1 from public.media_jobs as visible_job" in " ".join(
            body.split()
        )

    consume = function_sql(
        "consume_video_reservation", "claim_video_provider_launch"
    )
    settle = consume.index(
        "public.sweep_expired_video_leases(500, p_user_id, null)"
    )
    secondary = consume.index("pg_try_advisory_xact_lock", settle)
    row_lock = consume.index("for update skip locked", secondary)
    assert settle < secondary < row_lock
    assert "return query select 'settlement_pending'::text" in consume


def test_rolling_deploy_trigger_restores_identity_from_stale_new_metadata():
    trigger = function_sql(
        "normalize_pre_atomic_video_job", "authorize_video_reservation_capacity"
    )
    restore = trigger.index(
        "coalesce(old.metadata ->> 'compatibilityorigin', '') = 'pre-atomic'"
    )
    compatibility_decision = trigger.index("is_compatibility_row :=")
    early_return = trigger.index("if not is_compatibility_row")

    assert restore < compatibility_decision < early_return
    assert "new.idempotency_key := old.idempotency_key" in trigger
    assert "new.request_fingerprint := old.request_fingerprint" in trigger
    assert "'compatibilityrequestidentity', 'database-row-uuid-v1'" in trigger
    assert "and coalesce(old.metadata ->> 'compatibilityorigin', '') = 'pre-atomic'" in trigger


def test_finalizing_rows_reject_unfenced_stale_patches_and_preserve_control_metadata():
    trigger = function_sql(
        "normalize_pre_atomic_video_job", "authorize_video_reservation_capacity"
    )
    guard = trigger.split(
        "if tg_op = 'update' and old.video_phase = 'finalizing' then", 1
    )[1].split("-- old application updates can replace metadata wholesale", 1)[0]

    assert "new.video_phase in ('ready', 'failed')" in guard
    assert "new.status = new.video_phase" in guard
    assert "new.lease_token is null" in guard
    assert "new.finalization_started_at is null" in guard
    assert "new.video_phase = 'finalizing'" in guard
    assert "new.lease_token is distinct from old.lease_token" in guard
    assert "new.lease_expires_at is distinct from old.lease_expires_at" in guard
    assert "if not is_fenced_finalization_operation then return old" in " ".join(
        guard.split()
    )
    for key in (
        "finalizationoutcome",
        "finalizationrefundeligible",
        "finalizationstartedat",
        "finalizationexpiresat",
    ):
        assert f"old.metadata -> '{key}'" in guard


def test_migration_top_level_parser_keeps_trigger_and_function_bodies_atomic():
    statements = split_top_level_sql_statements(SQL)
    normalized_statements = [" ".join(item.lower().split()) for item in statements]

    assert normalized_statements[0].endswith("begin")
    assert normalized_statements[-1] == "commit"
    assert sum(
        "create or replace function public.normalize_pre_atomic_video_job()"
        in statement
        for statement in normalized_statements
    ) == 1
    assert sum(
        "create trigger media_jobs_pre_atomic_video_compatibility" in statement
        for statement in normalized_statements
    ) == 1
    assert sum(
        "update public.media_jobs set video_phase = video_phase" in statement
        for statement in normalized_statements
    ) == 1
    assert sum("create or replace function public." in item for item in normalized_statements) == 12
