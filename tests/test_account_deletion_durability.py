import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import httpx

from backend.account_deletion_service import AccountDeletionService
from backend.file_service import FileServiceError


ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, **values):
        self.value += timedelta(**values)


class DurableDeletionDB:
    def __init__(self, user_id='owner-user'):
        self.user = {
            'id': user_id,
            'deleted_at': None,
            'account_deletion_token': None,
            'native_billing_identity_possible_at': None,
            'ai_data_sharing_consent_at': '2026-09-17T23:55:00+00:00',
            'ai_data_sharing_consent_version': '2026-09-17',
            'ai_data_sharing_consent_revoked_at': None,
            'ai_data_sharing_consent_updated_at': '2026-09-17T23:55:00+00:00',
        }
        self.job = None
        self.insert_commit_then_error = False
        self.fence_commit_then_error = False
        self.rpc_error = False
        self.rpc_commit_then_error = False
        self.rpc_calls = 0
        self.native_snapshot_commit_then_error = False
        self.native_snapshot_failure = False

    @staticmethod
    def _expected(value):
        return str(value).removeprefix('eq.')

    async def insert(self, table, payload):
        assert table == 'account_deletion_jobs'
        if self.job:
            raise RuntimeError('duplicate account deletion owner')
        self.job = {'created_at': payload['fenced_at'], **dict(payload)}
        if self.insert_commit_then_error:
            self.insert_commit_then_error = False
            raise RuntimeError('response lost after durable job commit')
        return [dict(self.job)]

    async def update(self, table, payload, *, filters, retry_transient=False):
        if table == 'account_deletion_jobs':
            if not self.job:
                return []
            if self.job.get('completed_at') and filters.get('completed_at') == 'is.null':
                return []
            if self._expected(filters.get('user_id')) != self.job['user_id']:
                return []
            if self._expected(filters.get('operation_token')) != self.job['operation_token']:
                return []
            expected_attempts = filters.get('attempts')
            if (
                expected_attempts is not None
                and int(self._expected(expected_attempts)) != int(self.job.get('attempts') or 0)
            ):
                return []
            due = str(filters.get('next_attempt_at') or '')
            if due.startswith('lte.') and str(self.job.get('next_attempt_at') or '') > due[4:]:
                return []
            if payload.get('native_billing_identity_possible') and self.native_snapshot_failure:
                raise RuntimeError('native identity snapshot unavailable')
            self.job.update(payload)
            if payload.get('native_billing_identity_possible') and self.native_snapshot_commit_then_error:
                self.native_snapshot_commit_then_error = False
                raise RuntimeError('native identity snapshot response lost')
            return [dict(self.job)]

        assert table == 'users'
        if not self.user:
            return []
        if self._expected(filters.get('id')) != self.user['id']:
            return []
        if filters.get('deleted_at') == 'is.null' and self.user.get('deleted_at') is not None:
            return []
        if (
            filters.get('account_deletion_token') == 'is.null'
            and self.user.get('account_deletion_token') is not None
        ):
            return []
        self.user.update(payload)
        if self.fence_commit_then_error:
            self.fence_commit_then_error = False
            raise RuntimeError('response lost after fence commit')
        return [dict(self.user)]

    async def select_one(self, table, **_kwargs):
        if table == 'users':
            return dict(self.user) if self.user else None
        if table == 'account_deletion_jobs':
            return dict(self.job) if self.job else None
        raise AssertionError(table)

    async def select(
        self,
        table,
        *,
        columns='*',
        filters=None,
        order=None,
        limit=None,
    ):
        assert table == 'account_deletion_jobs'
        if not self.job or self.job.get('completed_at'):
            return []
        due = str((filters or {}).get('next_attempt_at') or '').removeprefix('lte.')
        if due and str(self.job.get('next_attempt_at') or '') > due:
            return []
        return [dict(self.job)]

    async def delete(self, table, *, filters):
        assert table == 'account_deletion_jobs'
        if not self.job:
            return []
        if self._expected(filters.get('user_id')) != self.job['user_id']:
            return []
        if self._expected(filters.get('operation_token')) != self.job['operation_token']:
            return []
        expected_attempts = filters.get('attempts')
        if (
            expected_attempts is not None
            and int(self._expected(expected_attempts)) != int(self.job.get('attempts') or 0)
        ):
            return []
        expected_due = filters.get('next_attempt_at')
        if (
            expected_due is not None
            and self._expected(expected_due) != str(self.job.get('next_attempt_at') or '')
        ):
            return []
        deleted = dict(self.job)
        self.job = None
        return [deleted]

    async def rpc(self, name, payload, retry_transient=False):
        assert name == 'delete_user_account'
        assert payload == {'p_user_id': 'owner-user'}
        self.rpc_calls += 1
        if self.rpc_commit_then_error:
            self.user = None
            self.rpc_commit_then_error = False
            raise RuntimeError('response lost after delete commit')
        if self.rpc_error:
            raise RuntimeError('database temporarily unavailable')
        self.user = None


class PrefixFiles:
    def __init__(self, objects=None):
        self.objects = set(objects or [])
        self.calls = 0
        self.failures = 0

    async def hard_delete_all_owned(self, *, user_id):
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise FileServiceError('storage unavailable', 503, 'STORAGE_ERROR')
        owned = {path for path in self.objects if path.startswith(f'{user_id}/')}
        self.objects.difference_update(owned)
        return len(owned)


def install_revenuecat_delete_sequence(monkeypatch, *outcomes):
    calls = []
    responses = iter(outcomes)

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def delete(self, url, **_kwargs):
            calls.append(url)
            outcome = next(responses)
            if isinstance(outcome, Exception):
                raise outcome
            return type('Response', (), {'status_code': outcome})()

    monkeypatch.setattr(httpx, 'AsyncClient', FakeClient)
    return calls


def native_deletion_service(database, files, clock, *, key='rc_test_fixture'):
    database.user['native_billing_identity_possible_at'] = clock().isoformat()
    return AccountDeletionService(
        database,
        files,
        now=clock,
        revenuecat_secret_api_key=key,
    )


def test_begin_reconciles_job_and_fence_commit_then_transport_errors():
    clock = Clock()
    database = DurableDeletionDB()
    database.insert_commit_then_error = True
    database.fence_commit_then_error = True
    service = AccountDeletionService(database, PrefixFiles(), now=clock)

    job = asyncio.run(service.begin(user_id='owner-user'))

    assert job['state'] == 'fenced'
    assert database.user['deleted_at'] is not None
    assert database.user['account_deletion_token'] == job['operation_token']
    assert (
        database.user['ai_data_sharing_consent_revoked_at']
        == database.user['deleted_at']
    )
    assert (
        database.user['ai_data_sharing_consent_updated_at']
        == database.user['deleted_at']
    )
    assert database.job['operation_token'] == job['operation_token']
    assert database.job['state'] == 'fenced'


def test_native_marker_is_snapshotted_after_fence_even_with_lost_write_response():
    clock = Clock()
    database = DurableDeletionDB()
    database.user['native_billing_identity_possible_at'] = clock().isoformat()
    database.native_snapshot_commit_then_error = True
    service = AccountDeletionService(database, PrefixFiles(), now=clock)

    job = asyncio.run(service.begin(user_id='owner-user'))

    assert job['native_billing_identity_possible'] is True
    assert database.job['native_billing_identity_possible'] is True
    assert database.user['deleted_at'] is not None


def test_unconfirmed_native_snapshot_blocks_local_deletion():
    clock = Clock()
    database = DurableDeletionDB()
    database.user['native_billing_identity_possible_at'] = clock().isoformat()
    database.native_snapshot_failure = True
    files = PrefixFiles({'owner-user/keep.png'})
    service = AccountDeletionService(database, files, now=clock)

    with pytest.raises(RuntimeError, match='cleanup evidence was not persisted'):
        asyncio.run(service.begin(user_id='owner-user'))
    clock.advance(minutes=16)
    progress = asyncio.run(service.process(database.job))

    assert progress.code == 'REVENUECAT_IDENTITY_MARK_UNCONFIRMED'
    assert database.user['deleted_at'] is not None
    assert database.rpc_calls == 0
    assert files.calls == 0
    assert files.objects == {'owner-user/keep.png'}


def test_concurrent_begin_converges_on_recent_durable_operation_token():
    clock = Clock()
    database = DurableDeletionDB()
    existing_token = '00000000-0000-4000-8000-000000000099'
    database.job = {
        'user_id': 'owner-user',
        'operation_token': existing_token,
        'state': 'fencing',
        'fenced_at': clock().isoformat(),
        'finalize_after': (clock() + timedelta(hours=30)).isoformat(),
        'next_attempt_at': (clock() + timedelta(minutes=15)).isoformat(),
        'attempts': 0,
        'last_error_code': None,
        'created_at': clock().isoformat(),
        'updated_at': clock().isoformat(),
    }
    service = AccountDeletionService(database, PrefixFiles(), now=clock)

    job = asyncio.run(service.begin(user_id='owner-user'))

    assert job['operation_token'] == existing_token
    assert database.user['account_deletion_token'] == existing_token
    assert database.job['operation_token'] == existing_token
    assert database.job['state'] == 'fenced'


def test_reentrant_begin_preserves_an_active_processing_lease():
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles({'owner-user/keep.png'})
    service = AccountDeletionService(database, files, now=clock)
    job = asyncio.run(service.begin(user_id='owner-user'))
    assert asyncio.run(service._claim_due_job(database.job)) is True
    lease_until = database.job['next_attempt_at']
    generation = database.job['attempts']

    resumed = asyncio.run(service.begin(user_id='owner-user'))
    progress = asyncio.run(service.process(resumed))

    assert resumed['operation_token'] == job['operation_token']
    assert database.job['next_attempt_at'] == lease_until
    assert database.job['attempts'] == generation
    assert progress.code == 'DELETION_JOB_IN_PROGRESS'
    assert files.calls == 0
    assert database.rpc_calls == 0


def test_expired_processing_lease_is_reclaimed_after_worker_crash():
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles({'owner-user/cleanup.png'})
    service = AccountDeletionService(database, files, now=clock)
    asyncio.run(service.begin(user_id='owner-user'))
    assert asyncio.run(service._claim_due_job(database.job)) is True
    abandoned_generation = database.job['attempts']

    clock.advance(minutes=service.PROCESS_LEASE_MINUTES + 1)
    summary = asyncio.run(service.process_due())

    assert summary == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert database.job['attempts'] > abandoned_generation
    assert database.user is None
    assert files.objects == set()


def test_reentrant_begin_cannot_reset_a_claimed_fencing_state():
    clock = Clock()
    database = DurableDeletionDB()
    service = AccountDeletionService(database, PrefixFiles(), now=clock)
    asyncio.run(service.begin(user_id='owner-user'))
    database.job['state'] = 'fencing'
    database.job['next_attempt_at'] = (
        clock() + timedelta(minutes=service.FENCE_RECONCILE_MINUTES)
    ).isoformat()
    clock.advance(minutes=service.FENCE_RECONCILE_MINUTES + 1)
    assert asyncio.run(service._claim_due_job(database.job)) is True
    lease_until = database.job['next_attempt_at']
    generation = database.job['attempts']

    asyncio.run(service.begin(user_id='owner-user'))

    assert database.job['state'] == 'fencing'
    assert database.job['next_attempt_at'] == lease_until
    assert database.job['attempts'] == generation


def test_late_uploads_are_swept_until_all_preissued_credentials_have_expired():
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles({'owner-user/original.png', 'other-user/keep.png'})
    service = AccountDeletionService(database, files, now=clock)
    job = asyncio.run(service.begin(user_id='owner-user'))

    initial = asyncio.run(service.process(job))

    assert initial.account_deleted is True
    assert initial.cleanup_complete is False
    assert database.user is None
    assert database.job['state'] == 'late_upload_sweep'
    assert files.objects == {'other-user/keep.png'}

    # A signed upload issued before the fence can land after the request's empty
    # prefix check. The durable hourly job must discover this metadata-less object.
    files.objects.add('owner-user/late-signed-upload.png')
    clock.advance(hours=1)
    hourly = asyncio.run(service.process_due())

    assert hourly == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert files.objects == {'other-user/keep.png'}
    assert database.job.get('completed_at') is None

    # The tombstone remains until after the combined signed/resumable credential
    # lifetime. Its last pass confirms the owner prefix again before completion.
    files.objects.add('owner-user/late-resumable-upload.mp4')
    clock.advance(hours=30)
    final = asyncio.run(service.process_due())

    assert final == {'processed': 1, 'deleted': 1, 'completed': 1, 'retrying': 0}
    assert files.objects == {'other-user/keep.png'}
    assert database.job is None


def test_repeated_revenuecat_200_keeps_native_job_after_thirty_hours(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles({'owner-user/initial.png'})
    calls = install_revenuecat_delete_sequence(monkeypatch, 200, 200, 200)
    service = native_deletion_service(database, files, clock)
    job = asyncio.run(service.begin(user_id='owner-user'))

    initial = asyncio.run(service.process(job))
    assert initial.account_deleted is True
    assert database.user is None
    assert database.job['native_billing_identity_possible'] is True

    files.objects.add('owner-user/late-upload.png')
    clock.advance(hours=31)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert database.job['last_error_code'] == 'REVENUECAT_CLEANUP_QUEUED'
    assert files.objects == set()

    clock.advance(minutes=16)
    repeat = asyncio.run(service.process_due())
    assert repeat == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert database.job is not None
    assert len(calls) == 3


def test_revenuecat_200_then_404_allows_same_sweep_final_purge(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    calls = install_revenuecat_delete_sequence(monkeypatch, 200, 404)
    service = native_deletion_service(database, files, clock)
    job = asyncio.run(service.begin(user_id='owner-user'))
    asyncio.run(service.process(job))

    clock.advance(hours=31)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 1, 'retrying': 0}
    assert database.job is None
    assert len(calls) == 2


@pytest.mark.parametrize('later_outcome', ['timeout', 'server_error', 'missing_key'])
def test_revenuecat_failure_after_local_deletion_keeps_job_and_sweeps_storage(
    monkeypatch, later_outcome
):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    later_response = {
        'timeout': httpx.ReadTimeout('provider timeout'),
        'server_error': 503,
        'missing_key': None,
    }[later_outcome]
    responses = (200,) if later_outcome == 'missing_key' else (200, later_response)
    calls = install_revenuecat_delete_sequence(monkeypatch, *responses)
    service = native_deletion_service(database, files, clock)
    job = asyncio.run(service.begin(user_id='owner-user'))
    asyncio.run(service.process(job))
    assert database.user is None

    files.objects.add('owner-user/late-upload.png')
    clock.advance(hours=31)
    if later_outcome == 'missing_key':
        service = AccountDeletionService(database, files, now=clock)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert database.job is not None
    assert database.job['native_billing_identity_possible'] is True
    assert database.job['last_error_code'] == 'REVENUECAT_CLEANUP_UNCONFIRMED'
    assert files.objects == set()
    assert files.calls == 2
    assert len(calls) == (1 if later_outcome == 'missing_key' else 2)


def test_revenuecat_404_earlier_does_not_validate_later_200_final_sweep(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    calls = install_revenuecat_delete_sequence(monkeypatch, 404, 200)
    service = native_deletion_service(database, files, clock)
    job = asyncio.run(service.begin(user_id='owner-user'))
    asyncio.run(service.process(job))

    clock.advance(hours=31)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert database.job['last_error_code'] == 'REVENUECAT_CLEANUP_QUEUED'
    assert len(calls) == 2


def test_overlapping_404_cannot_purge_a_newer_queued_200(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    calls = install_revenuecat_delete_sequence(monkeypatch, 200, 404, 200, 404)
    service = native_deletion_service(database, files, clock)
    job = asyncio.run(service.begin(user_id='owner-user'))
    asyncio.run(service.process(job))
    assert database.user is None
    clock.advance(hours=31)

    async def overlap():
        entered_storage = asyncio.Event()
        release_storage = asyncio.Event()
        original_cleanup = files.hard_delete_all_owned
        first_cleanup = True

        async def paused_cleanup(*, user_id):
            nonlocal first_cleanup
            if first_cleanup:
                first_cleanup = False
                entered_storage.set()
                await release_storage.wait()
            return await original_cleanup(user_id=user_id)

        files.hard_delete_all_owned = paused_cleanup
        first = asyncio.create_task(service.process_due())
        await asyncio.wait_for(entered_storage.wait(), timeout=2)
        first_generation = database.job['attempts']

        # The first worker's lease expires while it holds a stale 404. A
        # second worker sees a newly recreated provider customer and queues
        # its deletion. The first worker must not erase that new obligation.
        clock.advance(minutes=service.PROCESS_LEASE_MINUTES + 1)
        second = await service.process_due()
        assert second == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
        assert database.job['attempts'] > first_generation
        assert database.job['last_error_code'] == 'REVENUECAT_CLEANUP_QUEUED'

        release_storage.set()
        stale_first = await asyncio.wait_for(first, timeout=2)
        assert stale_first['completed'] == 0
        assert database.job is not None
        assert database.job['last_error_code'] == 'REVENUECAT_CLEANUP_QUEUED'

        clock.advance(minutes=16)
        final = await service.process_due()
        assert final == {'processed': 1, 'deleted': 1, 'completed': 1, 'retrying': 0}
        assert database.job is None

    asyncio.run(overlap())
    assert len(calls) == 4


def test_nonnative_deletion_purges_without_provider_request(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    calls = install_revenuecat_delete_sequence(monkeypatch)
    service = AccountDeletionService(
        database,
        files,
        now=clock,
    )
    job = asyncio.run(service.begin(user_id='owner-user'))
    asyncio.run(service.process(job))

    clock.advance(hours=31)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 1, 'retrying': 0}
    assert database.job is None
    assert calls == []


def test_unmarked_legacy_customer_is_durably_discovered_before_local_deletion(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    calls = install_revenuecat_delete_sequence(monkeypatch, 200, 200)
    service = AccountDeletionService(
        database,
        files,
        now=clock,
        revenuecat_secret_api_key='rc_test_fixture',
    )
    job = asyncio.run(service.begin(user_id='owner-user'))
    assert database.job['native_billing_identity_possible'] is False

    initial = asyncio.run(service.process(job))
    assert initial.account_deleted is True
    assert database.user is None
    assert database.job['native_billing_identity_possible'] is True

    clock.advance(hours=31)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert database.job['last_error_code'] == 'REVENUECAT_CLEANUP_QUEUED'
    assert len(calls) == 2


def test_unmarked_customer_cannot_be_deleted_if_provider_marker_write_fails(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    database.native_snapshot_failure = True
    files = PrefixFiles()
    calls = install_revenuecat_delete_sequence(monkeypatch, 200)
    service = AccountDeletionService(
        database,
        files,
        now=clock,
        revenuecat_secret_api_key='rc_test_fixture',
    )
    job = asyncio.run(service.begin(user_id='owner-user'))

    progress = asyncio.run(service.process(job))
    assert progress.code == 'REVENUECAT_IDENTITY_MARK_UNCONFIRMED'
    assert progress.retry_scheduled is True
    assert progress.account_deleted is False
    assert database.user is not None
    assert files.calls == 0
    assert database.rpc_calls == 0
    assert calls == []

    # A lost marker write fails before any provider request. Its retry code
    # keeps the obligation alive even if the key disappears on the next run.
    database.native_snapshot_failure = False
    clock.advance(minutes=16)
    missing_key_worker = AccountDeletionService(database, files, now=clock)
    retry = asyncio.run(missing_key_worker.process_due())
    assert retry == {'processed': 1, 'deleted': 0, 'completed': 0, 'retrying': 1}
    assert database.job['native_billing_identity_possible'] is True
    assert database.user is not None
    assert files.calls == 0
    assert database.rpc_calls == 0


def test_unmarked_customer_provider_404_allows_normal_final_purge(monkeypatch):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    calls = install_revenuecat_delete_sequence(monkeypatch, 404, 404)
    service = AccountDeletionService(
        database,
        files,
        now=clock,
        revenuecat_secret_api_key='rc_test_fixture',
    )
    job = asyncio.run(service.begin(user_id='owner-user'))
    initial = asyncio.run(service.process(job))
    assert initial.account_deleted is True
    assert database.job['native_billing_identity_possible'] is True

    clock.advance(hours=31)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 1, 'retrying': 0}
    assert database.job is None
    assert len(calls) == 2


@pytest.mark.parametrize(
    'prior_error',
    [
        'REVENUECAT_CLEANUP_UNCONFIRMED',
        'REVENUECAT_CLEANUP_QUEUED',
        'REVENUECAT_IDENTITY_MARK_UNCONFIRMED',
    ],
)
def test_legacy_provider_error_remains_an_obligation_without_native_flag(
    prior_error,
):
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles()
    service = AccountDeletionService(database, files, now=clock)
    job = asyncio.run(service.begin(user_id='owner-user'))
    asyncio.run(service.process(job))

    # An older job can carry the provider failure but not the newer marker.
    # Its error must be promoted to the durable obligation before purge.
    database.job['last_error_code'] = prior_error
    clock.advance(hours=31)
    final_sweep = asyncio.run(service.process_due())
    assert final_sweep == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert database.job['native_billing_identity_possible'] is True
    assert database.job['last_error_code'] == 'REVENUECAT_CLEANUP_UNCONFIRMED'


def test_failed_compensating_cleanup_keeps_fence_and_worker_recovers():
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles({'owner-user/object-left-by-failed-compensation.png'})
    files.failures = 1
    service = AccountDeletionService(database, files, now=clock)
    job = asyncio.run(service.begin(user_id='owner-user'))

    first = asyncio.run(service.process(job))

    assert first.account_deleted is False
    assert first.retry_scheduled is True
    assert database.user['deleted_at'] is not None
    assert database.rpc_calls == 0
    assert 'owner-user/object-left-by-failed-compensation.png' in files.objects
    assert database.job['state'] == 'retry_pending'

    clock.advance(minutes=15)
    recovered = asyncio.run(service.process_due())

    assert recovered['deleted'] == 1
    assert database.user is None
    assert 'owner-user/object-left-by-failed-compensation.png' not in files.objects
    assert database.job['state'] == 'late_upload_sweep'


def test_rpc_commit_then_error_is_reconciled_without_restoring_access():
    clock = Clock()
    database = DurableDeletionDB()
    database.rpc_commit_then_error = True
    service = AccountDeletionService(database, PrefixFiles(), now=clock)
    job = asyncio.run(service.begin(user_id='owner-user'))

    progress = asyncio.run(service.process(job))

    assert progress.account_deleted is True
    assert database.user is None
    assert database.rpc_calls == 1
    assert database.job['state'] == 'late_upload_sweep'


def test_stale_unfenced_job_expires_without_touching_active_account_storage():
    clock = Clock()
    database = DurableDeletionDB()
    files = PrefixFiles({'owner-user/active-account-file.png'})
    service = AccountDeletionService(database, files, now=clock)
    job = asyncio.run(service.begin(user_id='owner-user'))

    # Model a durable job whose user fence was never committed. A matching token
    # is required before the worker may touch the owner prefix.
    database.user['deleted_at'] = None
    database.user['account_deletion_token'] = None
    clock.advance(minutes=16)
    progress = asyncio.run(service.process(job))

    assert progress.code == 'DELETION_FENCE_NOT_ESTABLISHED'
    assert progress.retry_scheduled is False
    assert files.calls == 0
    assert files.objects == {'owner-user/active-account-file.png'}
    assert database.job['state'] == 'abandoned'
    assert database.job['completed_at'] is not None

    old_finalize_after = database.job['finalize_after']
    clock.advance(hours=2)
    replacement = asyncio.run(service.begin(user_id='owner-user'))

    assert replacement['operation_token'] != job['operation_token']
    assert database.job['state'] == 'fenced'
    assert database.job.get('completed_at') is None
    assert database.job['finalize_after'] > old_finalize_after
    assert database.user['account_deletion_token'] == replacement['operation_token']


def test_migration_keeps_cleanup_tombstone_service_role_only_and_outside_user_fk():
    migration = (
        ROOT / 'migrations' / '20260918043824_durable_account_deletion_storage_cleanup.sql'
    ).read_text(encoding='utf-8')

    assert 'add column if not exists account_deletion_token uuid' in migration
    assert 'create table if not exists public.account_deletion_jobs' in migration
    assert 'user_id uuid primary key' in migration
    assert 'references public.users' not in migration.lower()
    assert 'enable row level security' in migration
    assert 'from public, anon, authenticated, service_role' in migration
    assert 'to service_role' in migration

    consent_migration = (
        ROOT / 'migrations' / '20260918041136_ai_data_sharing_consent.sql'
    ).read_text(encoding='utf-8')
    assert 'ai_data_sharing_consent_revoked_at' in consent_migration
    assert 'ai_data_sharing_consent_updated_at' in consent_migration
    assert '20260918041136' < '20260918043824'

    shared_worker = (ROOT / 'backend' / 'routes' / 'manuscripts.py').read_text(
        encoding='utf-8'
    )
    assert 'account_deletions.process_due(limit=2)' in shared_worker
    assert shared_worker.index('account_deletions.process_due(limit=2)') < shared_worker.index(
        'code_worker.process_next('
    )
