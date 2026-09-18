import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
            self.job.update(payload)
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
