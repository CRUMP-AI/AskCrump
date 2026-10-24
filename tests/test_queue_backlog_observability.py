from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'migrations' / '20261024210302_queue_backlog_observability.sql'


def _migration() -> str:
    return MIGRATION.read_text(encoding='utf-8')


def _rpc_source() -> str:
    text = _migration()
    return text.split(
        'create or replace function public.read_email_queue_backlog_v1()', 1
    )[1].split('$function$;', 1)[0]


def test_queue_backlog_rpc_is_fixed_aggregate_only_and_content_free():
    text = _migration()
    source = _rpc_source()
    result = source.split('language sql', 1)[0]

    assert 'returns table (' in result
    assert result.count(' bigint') == 6
    assert 'verification_active_depth bigint' in result
    assert 'verification_eligible_depth bigint' in result
    assert 'verification_oldest_eligible_job_age_seconds bigint' in result
    assert 'password_reset_active_depth bigint' in result
    assert 'password_reset_eligible_depth bigint' in result
    assert 'password_reset_oldest_eligible_job_age_seconds bigint' in result
    for forbidden in (
        'id ', 'timestamp', 'json', 'status', 'failure', 'email', 'alias',
        'url', 'token', 'body', 'name',
    ):
        assert forbidden not in result.lower()

    assert source.count('pg_catalog.statement_timestamp()') == 1
    assert 'with sampled_clock as materialized (' in source
    assert source.count('union all') == 4
    assert source.count("job.status = 'queued'") == 4
    assert source.count("job.status = 'processing'") == 4
    assert source.count('job.attempts < 6') == 4
    assert "interval '5 minutes'" in source
    assert 'pg_catalog.make_interval(secs => 120)' in source
    assert "interval '23 hours'" in source
    assert "interval '55 minutes'" in source
    assert source.count('greatest(') == 2
    assert source.count('pg_catalog.floor(extract(') == 2
    assert 'public.verification_email_jobs' in source
    assert 'public.password_reset_email_jobs' in source
    assert not re.search(
        r'^\s*create\s+(?:unique\s+)?index\b', text, re.IGNORECASE | re.MULTILINE
    )
    assert not re.search(r'\b(begin|commit|rollback)\s*;', text, re.IGNORECASE)


def test_queue_backlog_security_and_drift_contract_is_bound():
    text = _migration()
    preflight = text.split('do $preflight$', 1)[1].split('$preflight$;', 1)[0]
    postflight = text.split('do $postflight$', 1)[1].split('$postflight$;', 1)[0]
    claim_guard = preflight.split(
        'foreach signature in array claim_signatures loop', 1
    )[1].split('end loop;', 1)[0]

    assert "language sql\nstable\nsecurity definer\nset search_path = ''" in text
    assert 'alter function public.read_email_queue_backlog_v1() owner to postgres;' in text
    assert (
        'revoke all on function public.read_email_queue_backlog_v1()\n'
        '  from public, anon, authenticated, service_role;'
    ) in text
    assert 'grant execute on function public.read_email_queue_backlog_v1() to service_role;' in text
    assert 'd6dd16c8e13ef88708663ec6b076f9ef' in text
    assert '800d71fa7c64b0e68f07c07a983b8c2e' in text
    assert text.count(
        "p_claim_token uuid, p_lease_seconds integer DEFAULT 120"
    ) == 1
    assert claim_guard.count(
        "pg_catalog.pg_get_expr(proc_row.proargdefaults, 0) is distinct from '120'"
    ) == 1
    assert "or proc_row.prokind <> 'f'" in claim_guard
    assert "or proc_row.proretset is not true" in claim_guard
    assert "or proc_row.pronargs <> 2" in claim_guard
    assert (
        "pg_catalog.pg_get_function_arguments(proc_row.oid)\n"
        "             is distinct from "
        "'p_claim_token uuid, p_lease_seconds integer DEFAULT 120'"
    ) in claim_guard
    assert (
        "pg_catalog.pg_get_function_result(proc_row.oid)\n"
        "             is distinct from "
        "'TABLE(job_id uuid, lease_token uuid, attempts integer)'"
    ) in claim_guard
    assert claim_guard.count('select pg_catalog.count(*) <> 2') == 1
    assert claim_guard.count("grantee_role.rolname = 'postgres'") == 1
    assert claim_guard.count("grantee_role.rolname = 'service_role'") == 1
    assert claim_guard.count("grantor_role.rolname = 'postgres'") == 2
    assert claim_guard.count("acl_row.privilege_type = 'EXECUTE'") == 2
    assert claim_guard.count('acl_row.is_grantable is false') == 2
    assert claim_guard.count(') <> 1') == 2

    def fk_trigger_fingerprint(table_variable: str, constraint_name: str) -> str:
        return (
            '(select pg_catalog.array_agg(\n'
            "       trigger_row.tgrelid::regclass::text || ':' || "
            "trigger_row.tgname || ':'\n"
            "         || trigger_row.tgenabled::text || ':' || "
            'trigger_row.tgisinternal::text\n'
            '       order by trigger_row.tgrelid::regclass::text, '
            'trigger_row.tgname\n'
            '     )::text\n'
            '     from pg_catalog.pg_trigger as trigger_row\n'
            '     join pg_catalog.pg_constraint as constraint_row\n'
            '       on constraint_row.oid = trigger_row.tgconstraint\n'
            f'     where constraint_row.conrelid = {table_variable}\n'
            f"       and constraint_row.conname = '{constraint_name}'\n"
            "       and constraint_row.contype = 'f')"
        )

    for phase in (preflight, postflight):
        assert phase.count(
            fk_trigger_fingerprint(
                'verification_table', 'verification_email_jobs_user_id_fkey'
            )
        ) == 1
        assert phase.count(
            fk_trigger_fingerprint(
                'password_reset_table', 'password_reset_email_jobs_user_id_fkey'
            )
        ) == 1
    assert text.count('efae7a5f9fb838ddcfbcdc4385f0b745') == 2
    assert "select pg_catalog.set_config('quote_all_identifiers', 'off', false);" in text
    assert 'expected_backlog_result constant text' in text
    assert 'verification_email_jobs changed during backlog migration.' in text
    assert 'password_reset_email_jobs changed during backlog migration.' in text


def test_both_workers_bind_the_same_120_second_lease_as_read_model():
    verification_worker = (
        ROOT / 'backend' / 'verification_email_queue.py'
    ).read_text(encoding='utf-8')
    password_worker = (
        ROOT / 'backend' / 'password_reset_email_queue.py'
    ).read_text(encoding='utf-8')
    exact_payload = "{'p_claim_token': claim_token, 'p_lease_seconds': 120}"

    assert verification_worker.count(exact_payload) == 1
    assert password_worker.count(exact_payload) == 1
    assert 'pg_catalog.make_interval(secs => 120)' in _rpc_source()


def test_queue_backlog_migration_is_bound_to_postgresql_17_11_gate():
    workflow = (
        ROOT / '.github' / 'workflows' / 'postgres-migration-gate.yml'
    ).read_text(encoding='utf-8')
    job = workflow.split('queue-backlog-observability:', 1)[1]

    assert 'image: postgres:17.11' in job
    assert 'password_reset_email_queue_baseline.sql' in job
    assert '20261024144202_durable_verification_email_jobs.sql' in job
    assert '20261024163849_durable_password_reset_email_jobs.sql' in job
    assert job.count('20261024210302_queue_backlog_observability.sql') >= 3
    assert 'test_queue_backlog_observability_first_apply_guards.sh' in job
    assert 'test_queue_backlog_observability_migration.sql' in job
    assert 'test_queue_backlog_observability_concurrency.sh' in job
    assert 'test_queue_backlog_observability_drift.sh' in job
    assert '--command=begin' in job
    assert '--command=rollback' in job
