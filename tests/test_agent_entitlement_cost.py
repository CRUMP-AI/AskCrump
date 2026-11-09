"""Registry entitlement and credit-cost enforcement for agent runs.

The registry's ``entitlement`` and credit-cost fields are enforced
server-side, at run creation and again at execution time:

- a ``paid`` capability rejects a caller without a verified paid
  entitlement with ``CAPABILITY_NOT_ENTITLED`` (403), and an
  ``account`` capability rejects guests the same way;
- a ``fixed``-cost capability rejects a caller whose credit balance
  (read through the existing credits authority) is below the exact
  registry cost with ``INSUFFICIENT_CREDITS`` (402), before any
  provider contact;
- a run created while entitled must not execute after the
  entitlement lapses or the balance drops — execution re-checks
  against current account state and leaves the run queued;
- the executor pause still sits ahead of every access check;
- free/account capabilities with a ``none`` cost pass through
  unchanged for entitled callers, and the gate never charges —
  charging stays charge-on-success through the existing mechanics.

Fixed-cost coverage uses a test-only capability built from the real
registry dataclass (a paid, fixed-cost variant of ``memory.list``,
whose executor adapter is the counting intelligence fake below). It
is patched into the run service's registry lookup for these tests
only; the production registry gains no entries.
"""
import pytest

from backend import agent_registry
from backend.agent_executor import AgentExecutor
from backend.agent_registry import Capability
from backend.agent_run_service import AgentRunError, AgentRunService
from test_agent_automations import FakeGoogleConnector

USER = '11111111-1111-1111-1111-111111111111'

FREE_ACCOUNT = {
    'id': USER,
    'is_guest': False,
    'subscription_tier': 'free',
    'subscription_status': 'inactive',
}
PRO_ACCOUNT = {
    'id': USER,
    'is_guest': False,
    'subscription_tier': 'professional',
    'subscription_status': 'active',
}
GUEST_ACCOUNT = {
    'id': USER,
    'is_guest': True,
    # A malformed paid-looking label must never entitle a guest.
    'subscription_tier': 'professional',
    'subscription_status': 'active',
}

FIXED_COST = 5
PAID_FIXED_MEMORY_LIST = Capability(
    id='memory.list',
    title='List what is remembered',
    verb_phrase='List what you remember about',
    input_schema={
        'type': 'object',
        'properties': {},
        'additionalProperties': False,
    },
    risk_class='read',
    approval='never',
    entitlement='paid',
    connector='internal',
    result_card='list',
    status='live',
    credit_cost_kind='fixed',
    credit_cost=FIXED_COST,
)


class FakeDB:
    """In-memory stand-in covering the run ledger, the users table,
    and the credit accounts the credits authority reads."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            'agent_runs': [],
            'agent_run_steps': [],
            'agent_pending_actions': [],
            'users': [],
            'credit_accounts': [],
        }
        self._step_id = 0

    def _matches(self, row, filters):
        for key, raw in (filters or {}).items():
            if isinstance(raw, str) and raw.startswith('eq.'):
                if str(row.get(key)) != raw[3:]:
                    return False
            elif isinstance(raw, str) and raw == 'is.null':
                if row.get(key) is not None:
                    return False
            elif row.get(key) != raw:
                return False
        return True

    async def select(self, table, *, columns='*', filters=None, order=None, limit=None):
        rows = [dict(r) for r in self.tables[table] if self._matches(r, filters)]
        if order:
            field, _, direction = order.partition('.')
            rows.sort(key=lambda r: str(r.get(field) or ''), reverse=direction == 'desc')
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def select_one(self, table, *, columns='*', filters=None):
        rows = await self.select(table, filters=filters, limit=1)
        return rows[0] if rows else None

    async def insert(self, table, payload):
        row = dict(payload)
        if table == 'agent_run_steps':
            self._step_id += 1
            row['id'] = self._step_id
        self.tables[table].append(row)
        return [row]

    async def update(self, table, payload, *, filters, **kwargs):
        updated = []
        for row in self.tables[table]:
            if self._matches(row, filters):
                row.update(payload)
                updated.append(dict(row))
        return updated


class CountingIntelligenceService:
    """Provider stand-in for the memory adapters: every call is a
    provider contact the gate must precede."""

    def __init__(self):
        self.list_calls: list[tuple] = []

    async def list_memories(self, user_id, *, limit=100):
        self.list_calls.append((user_id, limit))
        return [
            {
                'id': 'mem-1',
                'kind': 'preference',
                'created_at': '2026-11-01T10:00:00+00:00',
            }
        ]


def seed_account(db, account, *, balance=None):
    db.tables['users'] = [dict(account)]
    if balance is not None:
        db.tables['credit_accounts'] = [
            {
                'user_id': USER,
                'balance': balance,
                'lifetime_granted': balance,
                'lifetime_spent': 0,
            }
        ]
    return db.tables['users'][0]


def make_executor(db):
    service = AgentRunService(db)
    memory = CountingIntelligenceService()
    executor = AgentExecutor(
        service,
        google_connector=FakeGoogleConnector(connected=True),
        intelligence_service=memory,
        execution_paused=False,
    )
    return executor, service, memory


@pytest.fixture
def paid_fixed_registry(monkeypatch):
    real_get = agent_registry.get_capability

    def patched(capability_id):
        if capability_id == PAID_FIXED_MEMORY_LIST.id:
            return PAID_FIXED_MEMORY_LIST
        return real_get(capability_id)

    monkeypatch.setattr(
        'backend.agent_run_service.get_capability', patched
    )


# -- create-time entitlement ---------------------------------------------------


@pytest.mark.asyncio
async def test_paid_capability_create_rejects_free_account():
    db = FakeDB()
    seed_account(db, FREE_ACCOUNT, balance=100)
    service = AgentRunService(db)
    with pytest.raises(AgentRunError) as excinfo:
        await service.create_run(
            user_id=USER,
            capability_id='research.web_search',
            payload={'query': 'invoice'},
        )
    assert excinfo.value.code == 'CAPABILITY_NOT_ENTITLED'
    assert excinfo.value.status_code == 403
    assert db.tables['agent_runs'] == []


@pytest.mark.asyncio
async def test_paid_capability_create_rejects_guest_with_paid_label():
    db = FakeDB()
    seed_account(db, GUEST_ACCOUNT, balance=100)
    service = AgentRunService(db)
    with pytest.raises(AgentRunError) as excinfo:
        await service.create_run(
            user_id=USER,
            capability_id='research.web_search',
            payload={'query': 'invoice'},
        )
    assert excinfo.value.code == 'CAPABILITY_NOT_ENTITLED'


@pytest.mark.asyncio
async def test_account_capability_create_rejects_guest():
    db = FakeDB()
    seed_account(db, GUEST_ACCOUNT)
    service = AgentRunService(db)
    with pytest.raises(AgentRunError) as excinfo:
        await service.create_run(
            user_id=USER, capability_id='agent.today_brief', payload={}
        )
    assert excinfo.value.code == 'CAPABILITY_NOT_ENTITLED'
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_paid_quote_capability_create_allows_paid_account():
    # Quote-priced capabilities name no fixed figure in the registry;
    # the paid entitlement is their registry gate at creation.
    db = FakeDB()
    seed_account(db, PRO_ACCOUNT, balance=0)
    service = AgentRunService(db)
    run = await service.create_run(
        user_id=USER,
        capability_id='research.web_search',
        payload={'query': 'invoice'},
    )
    assert run['status'] == 'queued'


# -- create-time fixed cost ------------------------------------------------------


@pytest.mark.asyncio
async def test_fixed_cost_create_rejects_insufficient_balance(paid_fixed_registry):
    db = FakeDB()
    seed_account(db, PRO_ACCOUNT, balance=FIXED_COST - 1)
    service = AgentRunService(db)
    with pytest.raises(AgentRunError) as excinfo:
        await service.create_run(
            user_id=USER, capability_id='memory.list', payload={}
        )
    assert excinfo.value.code == 'INSUFFICIENT_CREDITS'
    assert excinfo.value.status_code == 402
    assert db.tables['agent_runs'] == []


# -- execute-time enforcement ------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_rejects_after_entitlement_lapses(paid_fixed_registry):
    db = FakeDB()
    account = seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service, memory = make_executor(db)
    run = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    assert run['status'] == 'queued'
    # The plan lapses after creation: the stored run must not execute.
    account['subscription_status'] = 'inactive'
    with pytest.raises(AgentRunError) as excinfo:
        await executor.execute_run(user_id=USER, run_id=run['id'])
    assert excinfo.value.code == 'CAPABILITY_NOT_ENTITLED'
    assert excinfo.value.status_code == 403
    assert memory.list_calls == []
    assert db.tables['agent_runs'][0]['status'] == 'queued'


@pytest.mark.asyncio
async def test_execute_rejects_when_balance_drops_below_cost(
    paid_fixed_registry,
):
    db = FakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service, memory = make_executor(db)
    run = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    db.tables['credit_accounts'][0]['balance'] = FIXED_COST - 1
    with pytest.raises(AgentRunError) as excinfo:
        await executor.execute_run(user_id=USER, run_id=run['id'])
    assert excinfo.value.code == 'INSUFFICIENT_CREDITS'
    assert excinfo.value.status_code == 402
    # The rejection lands before any provider contact.
    assert memory.list_calls == []
    assert db.tables['agent_runs'][0]['status'] == 'queued'


@pytest.mark.asyncio
async def test_fixed_cost_executes_with_sufficient_balance_and_exact_cost(
    paid_fixed_registry,
):
    db = FakeDB()
    seed_account(db, PRO_ACCOUNT, balance=100)
    executor, service, memory = make_executor(db)
    run = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    # The run carries the exact registry cost, never a caller figure.
    assert run['creditCost'] == FIXED_COST
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert memory.list_calls == [(USER, 100)]
    # The gate is a balance check only: it consumes nothing, so the
    # balance is untouched (charging stays charge-on-success through
    # the existing credits mechanics, which the executor never had).
    assert db.tables['credit_accounts'][0]['balance'] == 100


# -- pause ordering ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_stays_ahead_of_access_checks():
    db = FakeDB()
    seed_account(db, FREE_ACCOUNT, balance=0)
    service = AgentRunService(db)
    executor = AgentExecutor(
        service, google_connector=FakeGoogleConnector(connected=True)
    )
    run_id = '22222222-2222-2222-2222-222222222222'
    db.tables['agent_runs'].append(
        {
            'id': run_id,
            'user_id': USER,
            'project_id': None,
            'conversation_id': None,
            'capability_id': 'research.web_search',
            'status': 'queued',
            'input_payload': {'query': 'invoice'},
            'input_summary': {},
            'result_summary': None,
            'credit_cost': None,
            'created_at': '2026-11-09T00:00:00+00:00',
            'updated_at': '2026-11-09T00:00:00+00:00',
        }
    )
    with pytest.raises(AgentRunError) as excinfo:
        await executor.execute_run(user_id=USER, run_id=run_id)
    assert excinfo.value.code == 'AGENT_EXECUTION_PAUSED'
    assert db.tables['agent_runs'][0]['status'] == 'queued'


# -- unaffected live set -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_free_of_cost_set_passes_for_registered_free_account():
    db = FakeDB()
    seed_account(db, FREE_ACCOUNT)
    executor, service, memory = make_executor(db)

    run = await service.create_run(
        user_id=USER, capability_id='memory.list', payload={}
    )
    result = await executor.execute_run(user_id=USER, run_id=run['id'])
    assert result['status'] == 'succeeded'
    assert memory.list_calls == [(USER, 100)]

    for capability_id, payload in (
        ('agent.today_brief', {}),
        ('agent.morning_brief', {'schedule': 'daily 07:30 UTC'}),
    ):
        run = await service.create_run(
            user_id=USER, capability_id=capability_id, payload=payload
        )
        result = await executor.execute_run(user_id=USER, run_id=run['id'])
        assert result['status'] == 'succeeded'
