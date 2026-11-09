"""Agent capability registry.

The registry is the contract between the agent backend and the client.
The client renders task, approval, artifact, connection, and brief cards
from this metadata, so a new capability ships as a registry entry plus a
tool implementation, never as a client rewrite.

Rules that this module enforces at import time:

- Capability ids are stable, unique slugs. The model may only call
  registered capabilities; unknown ids fail closed.
- Risk class is assigned here, never inferred by the model.
- Read capabilities never require approval. Spend capabilities always
  render an approval card with the exact cost before the run.
- Credit cost is a rule evaluated before the run and charged on success
  only. ``fixed`` costs name the exact credit figure; ``quote`` costs are
  priced by the existing feature-quote path before any approval card is
  rendered; ``none`` capabilities never charge credits.
- ``status`` is honest: ``live`` capabilities are backed by a shipped
  implementation on main, ``planned`` capabilities are the Slice 1
  contract surface whose connector implementation has not landed yet,
  and ``gated`` capabilities exist but sit behind configuration or a
  release flag. Planned capabilities must not be presented as working.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REGISTRY_VERSION = '2026-11-08.1'

RISK_CLASSES = frozenset(
    {'read', 'write_reversible', 'write_irreversible', 'spend'}
)
APPROVAL_MODES = frozenset(
    {'never', 'card', 'card_with_cost', 'standing_rule_allowed'}
)
ENTITLEMENTS = frozenset({'free', 'account', 'paid'})
RESULT_CARDS = frozenset({'artifact', 'list', 'brief', 'plain'})
STATUSES = frozenset({'live', 'planned', 'gated'})


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    title: str
    verb_phrase: str
    input_schema: dict[str, Any]
    risk_class: str
    approval: str
    entitlement: str
    connector: str
    result_card: str
    status: str
    credit_cost_kind: str = 'none'
    credit_cost: int | None = None
    required_scopes: tuple[str, ...] = field(default_factory=tuple)

    def public_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'verbPhrase': self.verb_phrase,
            'inputSchema': self.input_schema,
            'riskClass': self.risk_class,
            'approval': self.approval,
            'creditCost': {
                'kind': self.credit_cost_kind,
                'credits': self.credit_cost,
                'chargeOnSuccess': True,
            },
            'entitlement': self.entitlement,
            'connector': self.connector,
            'requiredScopes': list(self.required_scopes),
            'resultCard': self.result_card,
            'status': self.status,
        }


def _schema(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    schema: dict[str, Any] = {
        'type': 'object',
        'properties': properties,
        'additionalProperties': False,
    }
    if required:
        schema['required'] = list(required)
    return schema


_CAPABILITIES: tuple[Capability, ...] = (
    # --- Live internal capabilities (shipped on main) -------------------
    Capability(
        id='chat.respond',
        title='Answer in conversation',
        verb_phrase='Answer',
        input_schema=_schema(
            {'message': {'type': 'string', 'minLength': 1}}, ('message',)
        ),
        risk_class='read',
        approval='never',
        entitlement='free',
        connector='internal',
        result_card='plain',
        status='live',
    ),
    Capability(
        id='research.web_search',
        title='Search the web',
        verb_phrase='Search the web for',
        input_schema=_schema(
            {'query': {'type': 'string', 'minLength': 1}}, ('query',)
        ),
        risk_class='read',
        approval='never',
        entitlement='paid',
        connector='brave',
        result_card='list',
        status='live',
        credit_cost_kind='quote',
    ),
    Capability(
        id='weather.lookup',
        title='Check the weather',
        verb_phrase='Check the weather for',
        input_schema=_schema(
            {'location': {'type': 'string', 'minLength': 1}}, ('location',)
        ),
        risk_class='read',
        approval='never',
        entitlement='paid',
        connector='openweather',
        result_card='brief',
        status='live',
        credit_cost_kind='quote',
    ),
    Capability(
        id='image.generate',
        title='Create an image',
        verb_phrase='Create an image of',
        input_schema=_schema(
            {'prompt': {'type': 'string', 'minLength': 1}}, ('prompt',)
        ),
        risk_class='write_reversible',
        approval='card_with_cost',
        entitlement='paid',
        connector='openai',
        result_card='artifact',
        status='live',
        credit_cost_kind='quote',
    ),
    Capability(
        id='video.generate',
        title='Create a video',
        verb_phrase='Create a video of',
        input_schema=_schema(
            {
                'prompt': {'type': 'string', 'minLength': 1},
                'mode': {
                    'type': 'string',
                    'enum': ['quick', 'extendable', 'cinematic'],
                },
            },
            ('prompt',),
        ),
        risk_class='spend',
        approval='card_with_cost',
        entitlement='paid',
        connector='internal',
        result_card='artifact',
        status='live',
        credit_cost_kind='quote',
    ),
    Capability(
        id='voice.synthesize',
        title='Read text aloud',
        verb_phrase='Read aloud',
        input_schema=_schema(
            {'text': {'type': 'string', 'minLength': 1}}, ('text',)
        ),
        risk_class='spend',
        approval='card_with_cost',
        entitlement='paid',
        connector='elevenlabs',
        result_card='artifact',
        status='live',
        credit_cost_kind='quote',
    ),
    Capability(
        id='code.task',
        title='Run a coding task',
        verb_phrase='Work on the code for',
        input_schema=_schema(
            {
                'projectId': {'type': 'string', 'minLength': 1},
                'objective': {'type': 'string', 'minLength': 1},
                'mode': {'type': 'string', 'enum': ['plan', 'implement']},
            },
            ('projectId', 'objective'),
        ),
        risk_class='write_reversible',
        approval='card',
        entitlement='paid',
        connector='internal',
        result_card='artifact',
        status='gated',
        credit_cost_kind='quote',
    ),
    Capability(
        id='files.manage',
        title='Work with files',
        verb_phrase='Work with the file',
        input_schema=_schema({'fileId': {'type': 'string', 'minLength': 1}}),
        risk_class='write_reversible',
        approval='card',
        entitlement='account',
        connector='internal',
        result_card='artifact',
        status='live',
    ),
    Capability(
        id='memory.user',
        title='Remember and forget',
        verb_phrase='Remember',
        input_schema=_schema(
            {'note': {'type': 'string', 'minLength': 1}}, ('note',)
        ),
        risk_class='write_reversible',
        approval='card',
        entitlement='account',
        connector='internal',
        result_card='plain',
        status='live',
    ),
    Capability(
        id='memory.list',
        title='List what is remembered',
        verb_phrase='List what you remember about',
        input_schema=_schema({}),
        risk_class='read',
        approval='never',
        entitlement='account',
        connector='internal',
        result_card='list',
        status='live',
    ),
    Capability(
        id='memory.forget',
        title='Forget a memory',
        verb_phrase='Forget',
        input_schema=_schema(
            {'memoryId': {'type': 'string', 'minLength': 1}}, ('memoryId',)
        ),
        risk_class='write_irreversible',
        approval='card',
        entitlement='account',
        connector='internal',
        result_card='plain',
        status='live',
    ),
    # --- Slice 1 planned capabilities (Google connector) ----------------
    Capability(
        id='gmail.search',
        title='Search your email',
        verb_phrase='Search your email for',
        input_schema=_schema(
            {
                'query': {'type': 'string', 'minLength': 1},
                'maxResults': {'type': 'integer', 'minimum': 1, 'maximum': 50},
            },
            ('query',),
        ),
        risk_class='read',
        approval='never',
        entitlement='account',
        connector='google',
        result_card='list',
        status='planned',
        required_scopes=('https://www.googleapis.com/auth/gmail.readonly',),
    ),
    Capability(
        id='gmail.read',
        title='Read an email',
        verb_phrase='Read the email',
        input_schema=_schema(
            {'messageId': {'type': 'string', 'minLength': 1}}, ('messageId',)
        ),
        risk_class='read',
        approval='never',
        entitlement='account',
        connector='google',
        result_card='plain',
        status='planned',
        required_scopes=('https://www.googleapis.com/auth/gmail.readonly',),
    ),
    Capability(
        id='calendar.list',
        title="List today's calendar",
        verb_phrase='Check your calendar for',
        input_schema=_schema(
            {
                'timeMin': {'type': 'string', 'format': 'date-time'},
                'timeMax': {'type': 'string', 'format': 'date-time'},
            }
        ),
        risk_class='read',
        approval='never',
        entitlement='account',
        connector='google',
        result_card='list',
        status='planned',
        required_scopes=('https://www.googleapis.com/auth/calendar.readonly',),
    ),
    Capability(
        id='calendar.create',
        title='Book a calendar event',
        verb_phrase='Book',
        input_schema=_schema(
            {
                'summary': {'type': 'string', 'minLength': 1},
                'start': {'type': 'string', 'format': 'date-time'},
                'end': {'type': 'string', 'format': 'date-time'},
                'attendees': {
                    'type': 'array',
                    'items': {'type': 'string', 'format': 'email'},
                },
            },
            ('summary', 'start', 'end'),
        ),
        risk_class='write_reversible',
        approval='card',
        entitlement='account',
        connector='google',
        result_card='brief',
        status='planned',
        required_scopes=('https://www.googleapis.com/auth/calendar.events',),
    ),
    Capability(
        id='agent.today_brief',
        title='Prepare the Today brief',
        verb_phrase='Prepare your brief',
        input_schema=_schema({}),
        risk_class='read',
        approval='never',
        entitlement='account',
        connector='internal',
        result_card='brief',
        status='live',
    ),
    Capability(
        id='agent.morning_brief',
        title='Send the morning brief',
        verb_phrase='Brief you every morning',
        input_schema=_schema(
            {'schedule': {'type': 'string', 'minLength': 1}}, ('schedule',)
        ),
        risk_class='read',
        approval='standing_rule_allowed',
        entitlement='account',
        connector='internal',
        result_card='brief',
        status='live',
    ),
    # --- Slice 2 planned capabilities -----------------------------------
    Capability(
        id='gmail.draft',
        title='Draft an email',
        verb_phrase='Draft an email to',
        input_schema=_schema(
            {
                'to': {'type': 'string', 'format': 'email'},
                'subject': {'type': 'string'},
                'body': {'type': 'string', 'minLength': 1},
            },
            ('to', 'body'),
        ),
        risk_class='write_reversible',
        approval='card',
        entitlement='account',
        connector='google',
        result_card='artifact',
        status='planned',
        required_scopes=('https://www.googleapis.com/auth/gmail.compose',),
    ),
    Capability(
        id='gmail.send',
        title='Send an email',
        verb_phrase='Send an email to',
        input_schema=_schema(
            {
                'to': {'type': 'string', 'format': 'email'},
                'subject': {'type': 'string'},
                'body': {'type': 'string', 'minLength': 1},
            },
            ('to', 'subject', 'body'),
        ),
        risk_class='write_irreversible',
        approval='card',
        entitlement='account',
        connector='google',
        result_card='plain',
        status='planned',
        required_scopes=('https://www.googleapis.com/auth/gmail.send',),
    ),
    Capability(
        id='browser.act',
        title='Act in the browser',
        verb_phrase='Open the browser and',
        input_schema=_schema(
            {'instruction': {'type': 'string', 'minLength': 1}},
            ('instruction',),
        ),
        risk_class='write_irreversible',
        approval='card',
        entitlement='paid',
        connector='internal',
        result_card='brief',
        status='planned',
        credit_cost_kind='quote',
    ),
    Capability(
        id='browser.read',
        title='Read a web page',
        verb_phrase='Read the page at',
        input_schema=_schema(
            {'url': {'type': 'string', 'minLength': 1}}, ('url',)
        ),
        risk_class='read',
        approval='never',
        entitlement='account',
        connector='internal',
        result_card='plain',
        status='live',
    ),
)

_BY_ID: dict[str, Capability] = {item.id: item for item in _CAPABILITIES}


def validate_registry() -> None:
    """Raise ValueError if any registry invariant is broken."""
    seen: set[str] = set()
    for item in _CAPABILITIES:
        if item.id in seen:
            raise ValueError(f'Duplicate capability id: {item.id}')
        seen.add(item.id)
        if item.risk_class not in RISK_CLASSES:
            raise ValueError(f'{item.id}: unknown risk class {item.risk_class}')
        if item.approval not in APPROVAL_MODES:
            raise ValueError(f'{item.id}: unknown approval mode {item.approval}')
        if item.entitlement not in ENTITLEMENTS:
            raise ValueError(f'{item.id}: unknown entitlement {item.entitlement}')
        if item.result_card not in RESULT_CARDS:
            raise ValueError(f'{item.id}: unknown result card {item.result_card}')
        if item.status not in STATUSES:
            raise ValueError(f'{item.id}: unknown status {item.status}')
        if not isinstance(item.input_schema, dict) or (
            item.input_schema.get('type') != 'object'
        ):
            raise ValueError(f'{item.id}: input schema must be a JSON object schema')
        if item.risk_class == 'read' and item.approval not in {
            'never',
            'standing_rule_allowed',
        }:
            raise ValueError(f'{item.id}: reads must not require an approval card')
        if item.risk_class == 'spend' and item.approval != 'card_with_cost':
            raise ValueError(f'{item.id}: spend always renders a card with cost')
        if item.risk_class == 'write_irreversible' and item.approval == 'never':
            raise ValueError(f'{item.id}: irreversible writes always require a card')
        if item.credit_cost_kind not in {'none', 'fixed', 'quote'}:
            raise ValueError(f'{item.id}: unknown credit cost kind')
        if item.credit_cost_kind == 'fixed' and not (
            isinstance(item.credit_cost, int) and item.credit_cost >= 0
        ):
            raise ValueError(f'{item.id}: fixed cost must name exact credits')
        if item.credit_cost_kind != 'fixed' and item.credit_cost is not None:
            raise ValueError(f'{item.id}: only fixed costs name a credit figure')
        if item.connector == 'google' and not item.required_scopes:
            raise ValueError(f'{item.id}: Google capabilities must name scopes')


validate_registry()


def capabilities() -> tuple[Capability, ...]:
    return _CAPABILITIES


def get_capability(capability_id: str) -> Capability | None:
    """Return the registered capability, or None. Unknown ids fail closed."""
    return _BY_ID.get(str(capability_id or '').strip())


def require_capability(capability_id: str) -> Capability:
    item = get_capability(capability_id)
    if item is None:
        raise KeyError(f'Unknown capability: {capability_id}')
    return item


def public_catalog() -> dict[str, Any]:
    return {
        'version': REGISTRY_VERSION,
        'capabilities': [item.public_dict() for item in _CAPABILITIES],
    }
