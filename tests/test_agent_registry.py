import json

import pytest

from app import app
from backend.agent_registry import (
    REGISTRY_VERSION,
    capabilities,
    get_capability,
    public_catalog,
    require_capability,
    validate_registry,
)
from conftest import iter_effective_routes

SLICE_ONE_IDS = {
    'gmail.search',
    'gmail.read',
    'calendar.list',
    'calendar.create',
    'agent.today_brief',
}


def test_registry_is_valid_and_versioned():
    validate_registry()
    assert REGISTRY_VERSION
    catalog = public_catalog()
    assert catalog['version'] == REGISTRY_VERSION
    json.dumps(catalog)


def test_capability_ids_are_unique():
    ids = [item.id for item in capabilities()]
    assert len(ids) == len(set(ids))


def test_slice_one_capabilities_are_registered():
    registered = {item.id for item in capabilities()}
    assert SLICE_ONE_IDS <= registered


def test_slice_one_google_capabilities_name_minimal_scopes():
    search = require_capability('gmail.search')
    assert search.connector == 'google'
    assert search.risk_class == 'read'
    assert search.approval == 'never'
    assert any('gmail.readonly' in scope for scope in search.required_scopes)

    create = require_capability('calendar.create')
    assert create.risk_class == 'write_reversible'
    assert create.approval == 'card'
    assert any('calendar.events' in scope for scope in create.required_scopes)


def test_planned_capabilities_are_not_presented_as_live():
    for capability_id in SLICE_ONE_IDS - {'agent.today_brief'}:
        assert require_capability(capability_id).status == 'planned'
    # The Today brief is self-contained and backed by the executor, so
    # it is the one Slice 1 capability that ships live.
    assert require_capability('agent.today_brief').status == 'live'


def test_unknown_capability_fails_closed():
    assert get_capability('gmail.delete_everything') is None
    assert get_capability('') is None
    with pytest.raises(KeyError):
        require_capability('gmail.delete_everything')


def test_spend_and_irreversible_capabilities_always_render_a_card():
    for item in capabilities():
        if item.risk_class == 'spend':
            assert item.approval == 'card_with_cost'
        if item.risk_class == 'write_irreversible':
            assert item.approval in {'card', 'card_with_cost'}
        if item.risk_class == 'read':
            assert item.approval in {'never', 'standing_rule_allowed'}


def test_public_catalog_shape_matches_the_card_contract():
    for entry in public_catalog()['capabilities']:
        assert entry['resultCard'] in {'artifact', 'list', 'brief', 'plain'}
        assert entry['creditCost']['chargeOnSuccess'] is True
        assert entry['status'] in {'live', 'planned', 'gated'}


def test_agent_capability_routes_are_registered():
    actual = {
        (method, route.path)
        for route in iter_effective_routes(app)
        for method in getattr(route, 'methods', set())
        if method not in {'HEAD', 'OPTIONS'}
    }
    assert ('GET', '/api/agent/capabilities') in actual
    assert ('GET', '/api/agent/capabilities/{capability_id}') in actual
