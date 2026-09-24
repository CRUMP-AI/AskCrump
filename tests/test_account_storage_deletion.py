import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend.account_deletion_service import AccountDeletionService
from backend.file_service import FileService, FileServiceError
from backend.routes import manuscripts as manuscript_routes


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'migrations' / '20260924210000_durable_account_storage_deletion.sql'
client = TestClient(app_module.app)
OWNER_ID = '11111111-1111-4111-8111-111111111111'
NEIGHBOR_ID = '11111111-1111-4111-8111-222222222222'


def file_service():
    settings = SimpleNamespace(
        storage_bucket='crump-files',
        supabase_url='https://example.supabase.co',
        supabase_service_key='test',
        max_upload_bytes=50 * 1024 * 1024,
    )
    return FileService(settings, SimpleNamespace())


class StorageHarness:
    def __init__(self, objects=()):
        self.objects = set(objects)
        self.calls = []
        self.fail_delete = False
        self.list_override = None

    async def request(self, method, path, *, payload=None, timeout=30.0):
        self.calls.append((method, path, payload, timeout))
        if method == 'POST' and path == 'object/list/crump-files':
            assert payload['offset'] == 0
            assert payload['limit'] == 1000
            if self.list_override is not None:
                return list(self.list_override)
            directory = payload['prefix'].strip('/')
            base = f'{directory}/'
            entries = {}
            for object_path in sorted(self.objects):
                if not object_path.startswith(base):
                    continue
                remainder = object_path[len(base):]
                name, separator, _rest = remainder.partition('/')
                if separator:
                    entries[name] = {'name': name, 'id': None, 'metadata': None}
                else:
                    entries[name] = {
                        'name': name,
                        'id': f'id-{name}',
                        'metadata': {'size': 1},
                    }
            return list(entries.values())[:1000]
        if method == 'DELETE' and path == 'object/crump-files':
            if self.fail_delete:
                raise FileServiceError('fixture failure', 503, 'STORAGE_ERROR')
            prefixes = list(payload.get('prefixes') or [])
            assert len(prefixes) <= 1000
            for object_path in prefixes:
                self.objects.discard(object_path)
            return prefixes
        raise AssertionError((method, path, payload))


def test_recursive_owner_purge_removes_direct_nested_retired_and_untracked_objects():
    target_objects = {
        f'{OWNER_ID}/direct.png',
        f'{OWNER_ID}/nested/reference.png',
        f'{OWNER_ID}/artifacts/report/versions/old.pdf',
        f'{OWNER_ID}/orphan-without-metadata.bin',
    }
    neighbor = f'{NEIGHBOR_ID}/must-remain.png'
    harness = StorageHarness(target_objects | {neighbor})
    files = file_service()
    files._storage_json = harness.request

    result = asyncio.run(
        files.purge_owner_prefix(
            user_id=OWNER_ID,
            owner_prefix=f'{OWNER_ID}/',
            bucket='crump-files',
        )
    )

    assert result == {
        'deletedCount': 4,
        'empty': True,
        'ownerPrefix': f'{OWNER_ID}/',
    }
    assert harness.objects == {neighbor}
    delete_batches = [
        payload['prefixes']
        for method, path, payload, _timeout in harness.calls
        if method == 'DELETE' and path == 'object/crump-files'
    ]
    assert all(path.startswith(f'{OWNER_ID}/') for batch in delete_batches for path in batch)
    assert all(len(batch) <= 1000 for batch in delete_batches)
    assert all(
        payload['offset'] == 0
        for method, path, payload, _timeout in harness.calls
        if method == 'POST' and path == 'object/list/crump-files'
    )


def test_owner_purge_re_lists_offset_zero_until_more_than_one_thousand_objects_are_gone():
    harness = StorageHarness(
        f'{OWNER_ID}/batch-{index:04d}.png'
        for index in range(1005)
    )
    files = file_service()
    files._storage_json = harness.request

    result = asyncio.run(files.purge_owner_prefix(user_id=OWNER_ID))

    assert result['deletedCount'] == 1005
    assert harness.objects == set()
    batches = [
        payload['prefixes']
        for method, _path, payload, _timeout in harness.calls
        if method == 'DELETE'
    ]
    assert [len(batch) for batch in batches] == [1000, 5]


def test_owner_purge_is_idempotent_when_prefix_is_already_empty():
    harness = StorageHarness()
    files = file_service()
    files._storage_json = harness.request

    first = asyncio.run(files.purge_owner_prefix(user_id=OWNER_ID))
    second = asyncio.run(files.purge_owner_prefix(user_id=OWNER_ID))

    assert first['deletedCount'] == 0
    assert second['deletedCount'] == 0
    assert all(method == 'POST' for method, *_rest in harness.calls)


@pytest.mark.parametrize(
    ('kwargs', 'expected_code'),
    [
        ({'user_id': 'not-a-uuid'}, 'INVALID_STORAGE_OWNER'),
        ({'user_id': OWNER_ID.replace('-', '')}, 'INVALID_STORAGE_OWNER'),
        (
            {'user_id': OWNER_ID, 'owner_prefix': f'{NEIGHBOR_ID}/'},
            'STORAGE_PREFIX_MISMATCH',
        ),
        (
            {'user_id': OWNER_ID, 'bucket': 'someone-elses-bucket'},
            'STORAGE_BUCKET_MISMATCH',
        ),
    ],
)
def test_owner_purge_rejects_non_exact_scope(kwargs, expected_code):
    files = file_service()
    with pytest.raises(FileServiceError) as caught:
        asyncio.run(files.purge_owner_prefix(**kwargs))
    assert caught.value.code == expected_code


def test_owner_purge_rejects_listing_path_escape_before_delete():
    harness = StorageHarness()
    harness.list_override = [
        {'name': '../must-not-delete.png', 'id': 'escape', 'metadata': {'size': 1}},
    ]
    files = file_service()
    files._storage_json = harness.request

    with pytest.raises(FileServiceError) as caught:
        asyncio.run(files.purge_owner_prefix(user_id=OWNER_ID))

    assert caught.value.code == 'STORAGE_PREFIX_ESCAPE'
    assert not any(method == 'DELETE' for method, *_rest in harness.calls)


def test_owner_purge_propagates_storage_failure_without_claiming_success():
    harness = StorageHarness({f'{OWNER_ID}/keep-until-retry.png'})
    harness.fail_delete = True
    files = file_service()
    files._storage_json = harness.request

    with pytest.raises(FileServiceError) as caught:
        asyncio.run(files.purge_owner_prefix(user_id=OWNER_ID))

    assert caught.value.code == 'STORAGE_ERROR'
    assert harness.objects == {f'{OWNER_ID}/keep-until-retry.png'}


class WorkerDB:
    def __init__(self, claim, *, completion=True, release='released'):
        self.claim = claim
        self.completion = completion
        self.release = release
        self.calls = []

    async def rpc(self, name, payload, **kwargs):
        self.calls.append((name, payload, kwargs))
        if name == 'claim_account_storage_deletion_job':
            return [self.claim] if self.claim else []
        if name == 'complete_account_storage_deletion_job':
            return self.completion
        if name == 'release_account_storage_deletion_job':
            return self.release
        raise AssertionError(name)


def claimed_job(*, final_delta, empty_delta=None):
    now = datetime.now(timezone.utc)
    return {
        'job_id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        'user_id': OWNER_ID,
        'bucket': 'crump-files',
        'owner_prefix': f'{OWNER_ID}/',
        'attempts': 1,
        'final_sweep_after': (now + final_delta).isoformat(),
        'empty_observed_at': (
            (now + empty_delta).isoformat()
            if empty_delta is not None
            else None
        ),
        'lease_token': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    }


def test_immediate_sweep_releases_job_until_the_27_hour_final_sweep():
    db = WorkerDB(
        claimed_job(final_delta=timedelta(hours=27)),
        release='awaiting_final_sweep',
    )
    files = SimpleNamespace(
        purge_owner_prefix=AsyncMock(return_value={'deletedCount': 3, 'empty': True}),
    )

    result = asyncio.run(AccountDeletionService(db, files).process_next())

    assert result['status'] == 'awaiting_final_sweep'
    assert [name for name, _payload, _kwargs in db.calls] == [
        'claim_account_storage_deletion_job',
        'release_account_storage_deletion_job',
    ]
    assert all(kwargs == {} for _name, _payload, kwargs in db.calls)


def test_final_sweep_starts_verification_then_second_empty_completes():
    first_db = WorkerDB(
        claimed_job(final_delta=timedelta(hours=-1)),
        release='verification_started',
    )
    files = SimpleNamespace(
        purge_owner_prefix=AsyncMock(return_value={'deletedCount': 0, 'empty': True}),
    )
    first = asyncio.run(AccountDeletionService(first_db, files).process_next())
    assert first['status'] == 'verification_started'
    assert not any(name == 'complete_account_storage_deletion_job' for name, *_rest in first_db.calls)

    second_db = WorkerDB(
        claimed_job(
            final_delta=timedelta(hours=-1),
            empty_delta=timedelta(minutes=-6),
        )
    )
    second = asyncio.run(AccountDeletionService(second_db, files).process_next())
    assert second['status'] == 'completed'
    assert [name for name, _payload, _kwargs in second_db.calls][-1] == (
        'complete_account_storage_deletion_job'
    )


def test_late_object_after_first_empty_observation_resets_verification():
    db = WorkerDB(
        claimed_job(
            final_delta=timedelta(hours=-1),
            empty_delta=timedelta(minutes=-6),
        ),
        release='verification_started',
    )
    files = SimpleNamespace(
        purge_owner_prefix=AsyncMock(return_value={'deletedCount': 1, 'empty': True}),
    )

    result = asyncio.run(AccountDeletionService(db, files).process_next())

    assert result['status'] == 'verification_started'
    assert not any(name == 'complete_account_storage_deletion_job' for name, *_rest in db.calls)
    release_payload = next(payload for name, payload, _kwargs in db.calls if name.startswith('release_'))
    assert release_payload['p_objects_deleted'] == 1


def test_storage_failure_is_released_for_retry_without_exposing_error_text():
    db = WorkerDB(claimed_job(final_delta=timedelta(hours=27)))
    files = SimpleNamespace(
        purge_owner_prefix=AsyncMock(
            side_effect=FileServiceError('signed URL secret fixture', 503, 'STORAGE_ERROR')
        ),
    )

    result = asyncio.run(AccountDeletionService(db, files).process_next())

    assert result == {
        'handled': True,
        'status': 'retry_scheduled',
        'errorCode': 'STORAGE_ERROR',
    }
    release_payload = next(payload for name, payload, _kwargs in db.calls if name.startswith('release_'))
    assert release_payload['p_error'] == 'STORAGE_ERROR'
    assert 'secret' not in json.dumps(release_payload)


def test_stale_completion_token_cannot_report_completion():
    db = WorkerDB(
        claimed_job(
            final_delta=timedelta(hours=-1),
            empty_delta=timedelta(minutes=-6),
        ),
        completion=False,
        release='lease_lost',
    )
    files = SimpleNamespace(
        purge_owner_prefix=AsyncMock(return_value={'deletedCount': 0, 'empty': True}),
    )

    result = asyncio.run(AccountDeletionService(db, files).process_next())

    assert result['status'] == 'lease_lost'
    assert [name for name, _payload, _kwargs in db.calls][-2:] == [
        'complete_account_storage_deletion_job',
        'release_account_storage_deletion_job',
    ]


def test_existing_minute_cron_prioritizes_one_account_storage_purge(monkeypatch):
    deletion_worker = SimpleNamespace(
        process_next=AsyncMock(return_value={'handled': True, 'status': 'completed'})
    )
    code_worker = SimpleNamespace(process_next=AsyncMock(return_value={'handled': False}))
    manuscript_worker = SimpleNamespace(process_next_run=AsyncMock(return_value={'handled': False}))
    monkeypatch.setattr(manuscript_routes, 'account_deletions', deletion_worker)
    monkeypatch.setattr(manuscript_routes, 'code_worker', code_worker)
    monkeypatch.setattr(manuscript_routes, 'manuscripts', manuscript_worker)
    monkeypatch.setattr(
        manuscript_routes,
        'settings',
        SimpleNamespace(cron_secret='cron-secret', vercel_oidc_token=None),
    )

    response = client.get(
        '/api/cron/manuscripts',
        headers={'Authorization': 'Bearer cron-secret'},
    )

    assert response.status_code == 200
    assert response.json()['worker'] == 'account-storage-deletion'
    deletion_worker.process_next.assert_awaited_once()
    code_worker.process_next.assert_not_awaited()
    manuscript_worker.process_next_run.assert_not_awaited()


def test_idle_account_storage_queue_preserves_existing_code_worker(monkeypatch):
    deletion_worker = SimpleNamespace(
        process_next=AsyncMock(return_value={'handled': False, 'status': 'idle'})
    )
    code_worker = SimpleNamespace(
        process_next=AsyncMock(return_value={'handled': True, 'status': 'completed'})
    )
    manuscript_worker = SimpleNamespace(process_next_run=AsyncMock(return_value={'handled': False}))
    monkeypatch.setattr(manuscript_routes, 'account_deletions', deletion_worker)
    monkeypatch.setattr(manuscript_routes, 'code_worker', code_worker)
    monkeypatch.setattr(manuscript_routes, 'manuscripts', manuscript_worker)
    monkeypatch.setattr(
        manuscript_routes,
        'settings',
        SimpleNamespace(cron_secret='cron-secret', vercel_oidc_token='oidc-token'),
    )

    response = client.get(
        '/api/cron/manuscripts',
        headers={'Authorization': 'Bearer cron-secret'},
    )

    assert response.status_code == 200
    assert response.json()['worker'] == 'code'
    deletion_worker.process_next.assert_awaited_once()
    code_worker.process_next.assert_awaited_once_with(oidc_token='oidc-token')
    manuscript_worker.process_next_run.assert_not_awaited()


def test_migration_contract_enqueues_before_delete_and_fences_all_worker_transitions():
    sql = MIGRATION.read_text(encoding='utf-8').lower()
    compact = ' '.join(sql.split())
    table_section = sql.split(
        'create table if not exists public.account_storage_deletion_jobs',
        1,
    )[1].split(');', 1)[0]

    assert 'references public.users' not in table_section
    assert "owner_prefix = user_id::text || '/'" in sql
    assert "interval '27 hours'" in sql
    assert "interval '5 minutes'" in sql
    assert 'for update skip locked' in compact
    assert "job.status = 'processing' and job.lease_expires_at <=" in compact
    assert 'and job.lease_token = p_lease_token' in compact
    assert sql.index('insert into public.account_storage_deletion_jobs') < sql.index(
        'delete from public.users'
    )
    assert 'delete from storage.objects' not in sql
    assert 'p_storage_bucket text' in sql
    assert "or p_storage_bucket !~ '^[a-za-z0-9][a-za-z0-9._-]{0,99}$'" in sql
    assert "perform public.delete_user_account(p_user_id, 'crump-files')" in sql
    assert 'alter table public.account_storage_deletion_jobs enable row level security' in sql
    for signature in (
        'public.claim_account_storage_deletion_job()',
        'public.release_account_storage_deletion_job(uuid, uuid, integer, text)',
        'public.complete_account_storage_deletion_job(uuid, uuid)',
        'public.delete_user_account(uuid, text)',
        'public.delete_user_account(uuid)',
    ):
        assert f'revoke all on function {signature} from public, anon, authenticated' in compact
        assert f'grant execute on function {signature} to service_role' in compact


def test_existing_cron_slot_is_reused_and_storage_purge_runs_first():
    vercel = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
    source = (ROOT / 'backend' / 'routes' / 'manuscripts.py').read_text(encoding='utf-8')

    assert [entry['path'] for entry in vercel['crons']] == [
        '/api/cron/check-ins',
        '/api/cron/manuscripts',
        '/api/cron/videos',
    ]
    assert source.index('account_deletions.process_next()') < source.index(
        'code_worker.process_next('
    )
    assert source.index('account_deletions.process_next()') < source.index(
        'manuscripts.process_next_run()'
    )
