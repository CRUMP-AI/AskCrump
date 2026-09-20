"""Native SDK identity evidence must be durable before RevenueCat can start."""

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import app
from backend.routes import billing as billing_routes


client = TestClient(app)
OWNER = '00000000-0000-4000-8000-000000000123'
ROOT = Path(__file__).resolve().parents[1]


class IdentityDB:
    def __init__(self):
        self.user = {
            'id': OWNER,
            'deleted_at': None,
            'account_deletion_token': None,
            'native_billing_identity_possible_at': None,
        }
        self.writes = 0
        self.commit_then_error = False
        self.reject_write = False
        self.reject_read = False

    async def update(self, table, payload, *, filters, retry_transient=False):
        assert table == 'users'
        assert retry_transient is True
        assert filters == {
            'id': f'eq.{OWNER}',
            'deleted_at': 'is.null',
            'account_deletion_token': 'is.null',
            'native_billing_identity_possible_at': 'is.null',
        }
        self.writes += 1
        if self.reject_write:
            raise RuntimeError('database unavailable')
        if (
            self.user['deleted_at']
            or self.user['account_deletion_token']
            or self.user['native_billing_identity_possible_at']
        ):
            return []
        self.user.update(payload)
        if self.commit_then_error:
            raise RuntimeError('database response lost')
        return [dict(self.user)]

    async def select_one(self, table, *, columns, filters):
        assert table == 'users'
        assert 'native_billing_identity_possible_at' in columns
        assert filters == {'id': f'eq.{OWNER}'}
        if self.reject_read:
            raise RuntimeError('database read unavailable')
        return dict(self.user) if self.user else None


def setup_identity(monkeypatch, *, enabled=True):
    database = IdentityDB()

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': OWNER})

    monkeypatch.setattr(billing_routes, 'db', database)
    monkeypatch.setattr(billing_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(
        billing_routes,
        'settings',
        SimpleNamespace(native_billing_enabled=enabled),
    )
    return database


def test_server_authoritative_identity_marker_is_monotonic(monkeypatch):
    database = setup_identity(monkeypatch)

    first = client.post(
        '/api/billing/native-identity',
        json={'userId': '00000000-0000-4000-8000-000000000999'},
    )
    marked_at = database.user['native_billing_identity_possible_at']
    second = client.post('/api/billing/native-identity')

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {
        'success': True,
        'recorded': True,
        'userId': OWNER,
    }
    assert first.headers['cache-control'] == 'no-store'
    assert marked_at and database.user['native_billing_identity_possible_at'] == marked_at


def test_commit_then_transport_error_is_confirmed_by_readback(monkeypatch):
    database = setup_identity(monkeypatch)
    database.commit_then_error = True

    response = client.post('/api/billing/native-identity')

    assert response.status_code == 200
    assert response.json()['userId'] == OWNER
    assert database.user['native_billing_identity_possible_at']


def test_unconfirmed_marker_blocks_native_sdk_setup(monkeypatch):
    database = setup_identity(monkeypatch)
    database.reject_write = True

    response = client.post('/api/billing/native-identity')

    assert response.status_code == 503
    assert response.json()['code'] == 'NATIVE_IDENTITY_MARK_UNCONFIRMED'
    assert database.user['native_billing_identity_possible_at'] is None


def test_unconfirmed_readback_blocks_native_sdk_setup(monkeypatch):
    database = setup_identity(monkeypatch)
    database.reject_read = True

    response = client.post('/api/billing/native-identity')

    assert response.status_code == 503
    assert response.json()['code'] == 'NATIVE_IDENTITY_MARK_UNCONFIRMED'
    assert database.user['native_billing_identity_possible_at']


def test_deletion_fence_blocks_native_sdk_setup(monkeypatch):
    database = setup_identity(monkeypatch)
    database.user['account_deletion_token'] = '00000000-0000-4000-8000-000000000777'
    database.user['deleted_at'] = '2026-09-20T12:00:00+00:00'

    response = client.post('/api/billing/native-identity')

    assert response.status_code == 409
    assert response.json()['code'] == 'ACCOUNT_UNAVAILABLE'
    assert database.user['native_billing_identity_possible_at'] is None


def test_deleted_account_row_blocks_native_sdk_setup(monkeypatch):
    database = setup_identity(monkeypatch)
    database.user = None

    response = client.post('/api/billing/native-identity')

    assert response.status_code == 409
    assert response.json()['code'] == 'ACCOUNT_UNAVAILABLE'


def test_disabled_native_billing_never_marks_an_sdk_identity(monkeypatch):
    database = setup_identity(monkeypatch, enabled=False)

    response = client.post('/api/billing/native-identity')

    assert response.status_code == 503
    assert response.json()['code'] == 'NATIVE_BILLING_NOT_READY'
    assert database.writes == 0


def test_native_identity_schema_follows_durable_deletion_without_new_public_grants():
    migration = (
        ROOT / 'migrations' / '20260920233907_native_billing_identity_cleanup.sql'
    ).read_text(encoding='utf-8')

    assert '20260918043824' < '20260920233907'
    assert 'add column if not exists native_billing_identity_possible_at timestamptz' in migration
    assert 'add column if not exists native_billing_identity_possible boolean not null default false' in migration
    assert 'grant ' not in migration.lower()
    assert 'create table' not in migration.lower()
