from __future__ import annotations

from pathlib import Path
import re
import pytest
from fastapi import Request
from pydantic import ValidationError

from backend.product_analytics import (
    ATTRIBUTION_CAMPAIGNS,
    normalize_attribution,
    record_account_created_event,
)
from backend.routes import auth as auth_routes
from backend.schemas import RegisterRequest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260830171056_weekly_growth_attribution_export.sql"
EXPECTED_REGISTRY = {
    "presentation-proof-current": {
        "intent": "presentation",
        "acquisitions": {"facebook", "instagram"},
        "placements": {"profile-link", "organic-social"},
        "creatives": {"fb-static", "ig-feed", "ig-story"},
    },
    "real-product-continuity": {
        "intent": "projects",
        "acquisitions": {"facebook", "instagram"},
        "placements": {"profile-link", "organic-social"},
        "creatives": {"continuity-feed", "continuity-story"},
    },
    "rough-idea-launch-plan": {
        "intent": "projects",
        "acquisitions": {"organic-search"},
        "placements": {"workflow-guide"},
        "creatives": {"search-article"},
    },
    "project-memory-boundaries": {
        "intent": "projects",
        "acquisitions": {"organic-search", "facebook", "instagram"},
        "placements": {"workflow-guide", "organic-social"},
        "creatives": {"search-article", "project-memory-feed", "project-memory-story"},
    },
    "editable-powerpoint-review": {
        "intent": "presentation",
        "acquisitions": {"organic-search", "facebook", "instagram"},
        "placements": {"workflow-guide", "organic-social"},
        "creatives": {"search-article", "presentation-feed", "presentation-story"},
    },
    "creator-cohort-01": {
        "intent": "projects",
        "acquisitions": {"founder-outreach"},
        "placements": {"creator-cohort"},
        "creatives": {"personal-invite"},
    },
}


def request_for(host: str, platform: str = "web") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "scheme": "https",
        "server": (host, 443),
        "path": "/api/auth/register",
        "query_string": b"",
        "headers": [(b"x-crump-platform", platform.encode("ascii"))],
    })


def _parse_js_registry(source: str) -> dict[str, dict[str, object]]:
    block_match = re.search(
        r"const CAMPAIGN_REGISTRY = Object\.freeze\(\{(.*?)\n  \}\);",
        source,
        re.DOTALL,
    )
    assert block_match
    entry_pattern = re.compile(
        r"'([^']+)': \{\s*"
        r"intent: '([^']+)',\s*"
        r"acquisitions: new Set\(\[([^\]]*)\]\),\s*"
        r"placements: new Set\(\[([^\]]*)\]\),\s*"
        r"creatives: new Set\(\[([^\]]*)\]\),\s*\}",
        re.DOTALL,
    )

    def values(raw: str) -> set[str]:
        return set(re.findall(r"'([^']+)'", raw))

    return {
        campaign: {
            "intent": intent,
            "acquisitions": values(acquisitions),
            "placements": values(placements),
            "creatives": values(creatives),
        }
        for campaign, intent, acquisitions, placements, creatives
        in entry_pattern.findall(block_match.group(1))
    }


def _sql_values(branch: str, field: str) -> set[str]:
    match = re.search(
        rf"\b{field}\s+in\s+\(([^)]*)\)|\b{field}\s*=\s*'([^']+)'",
        branch,
    )
    assert match, (field, branch)
    if match.group(2):
        return {match.group(2)}
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _parse_sql_constraint_registry(sql: str) -> dict[str, dict[str, object]]:
    start = sql.index("product_events_campaign_registry_check")
    block = sql[start:sql.index("end if;", start)]
    matches = list(re.finditer(r"(?m)^\s+campaign = '([^']+)'", block))
    parsed = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        branch = block[match.start():end]
        parsed[match.group(1)] = {
            "intent": next(iter(_sql_values(branch, "intent"))),
            "acquisitions": _sql_values(branch, "source"),
            "placements": _sql_values(branch, "placement"),
            "creatives": _sql_values(branch, "creative"),
        }
    return parsed


def _parse_sql_rpc_registry(sql: str) -> dict[str, dict[str, object]]:
    function_start = sql.index("create or replace function public.record_account_created_event")
    validation_start = sql.index("if not (", function_start)
    validation_end = sql.index("v_campaign := null;", validation_start)
    block = sql[validation_start:validation_end]
    matches = list(re.finditer(r"(?m)^\s+v_campaign = '([^']+)'", block))
    parsed = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        branch = block[match.start():end]
        parsed[match.group(1)] = {
            "intent": next(iter(_sql_values(branch, "v_intent"))),
            "acquisitions": _sql_values(branch, "v_acquisition"),
            "placements": _sql_values(branch, "v_placement"),
            "creatives": set(),
        }

    creative_start = sql.index("if v_campaign is null or not (", validation_end)
    creative_end = sql.index("v_creative := null;", creative_start)
    creative_block = sql[creative_start:creative_end]
    creative_matches = re.findall(
        r"v_campaign = '([^']+)' and v_creative\s+"
        r"(?:in \(([^)]*)\)|= '([^']+)')",
        creative_block,
    )
    for campaign, multiple, single in creative_matches:
        parsed[campaign]["creatives"] = (
            set(re.findall(r"'([^']+)'", multiple)) if multiple else {single}
        )
    return parsed


class RPCDB:
    def __init__(self, *, result=True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def rpc(self, function_name, payload):
        self.calls.append((function_name, dict(payload)))
        if self.error:
            raise self.error
        return self.result


def test_campaign_registry_has_exact_frontend_server_and_database_parity():
    landing = (ROOT / "public" / "landing.js").read_text(encoding="utf-8")
    controller = (ROOT / "public" / "auth-controller.js").read_text(encoding="utf-8")
    sql = MIGRATION.read_text(encoding="utf-8")
    python_registry = {
        campaign: {
            "intent": values["intent"],
            "acquisitions": set(values["acquisitions"]),
            "placements": set(values["placements"]),
            "creatives": set(values["creatives"]),
        }
        for campaign, values in ATTRIBUTION_CAMPAIGNS.items()
    }

    assert python_registry == EXPECTED_REGISTRY
    assert _parse_js_registry(landing) == EXPECTED_REGISTRY
    assert _parse_js_registry(controller) == EXPECTED_REGISTRY
    assert _parse_sql_constraint_registry(sql) == EXPECTED_REGISTRY
    assert _parse_sql_rpc_registry(sql) == EXPECTED_REGISTRY


def test_registered_campaign_tuple_is_preserved_exactly():
    assert normalize_attribution(
        acquisition="Instagram",
        placement="profile-link",
        campaign="presentation-proof-current",
        creative="ig-feed",
        intent="presentation",
    ) == {
        "acquisition": "instagram",
        "placement": "profile-link",
        "campaign": "presentation-proof-current",
        "creative": "ig-feed",
        "intent": "presentation",
    }

    assert normalize_attribution(
        acquisition="facebook",
        placement="organic-social",
        campaign="real-product-continuity",
        creative="continuity-feed",
        intent="projects",
    ) == {
        "acquisition": "facebook",
        "placement": "organic-social",
        "campaign": "real-product-continuity",
        "creative": "continuity-feed",
        "intent": "projects",
    }


@pytest.mark.parametrize(
    "values, expected",
    [
        (
            {
                "acquisition": "https://example.com/path",
                "placement": "free text",
                "campaign": "unknown-campaign",
                "creative": "person@example.com",
                "intent": "prompt text",
            },
            {
                "acquisition": None,
                "placement": None,
                "campaign": None,
                "creative": None,
                "intent": None,
            },
        ),
        (
            {
                "acquisition": "facebook",
                "placement": "profile-link",
                "campaign": "presentation-proof-current",
                "creative": "not-registered",
                "intent": "presentation",
            },
            {
                "acquisition": "facebook",
                "placement": "profile-link",
                "campaign": "presentation-proof-current",
                "creative": None,
                "intent": "presentation",
            },
        ),
        (
            {
                "acquisition": "organic-search",
                "placement": "workflow-guide",
                "campaign": "presentation-proof-current",
                "creative": "ig-feed",
                "intent": "presentation",
            },
            {
                "acquisition": "organic-search",
                "placement": "workflow-guide",
                "campaign": None,
                "creative": None,
                "intent": "presentation",
            },
        ),
    ],
)
def test_unknown_content_or_registry_mismatches_are_discarded(values, expected):
    assert normalize_attribution(**values) == expected


@pytest.mark.asyncio
async def test_account_created_writer_sends_only_the_allowlisted_tuple():
    database = RPCDB()
    recorded = await record_account_created_event(
        database,
        user_id="00000000-0000-0000-0000-000000000001",
        request=request_for("www.askcrump.com", "ios"),
        acquisition="instagram",
        placement="profile-link",
        campaign="presentation-proof-current",
        creative="ig-feed",
        intent="presentation",
    )

    assert recorded is True
    assert database.calls == [(
        "record_account_created_event",
        {
            "p_user_id": "00000000-0000-0000-0000-000000000001",
            "p_event_key": "account-created",
            "p_environment": "production",
            "p_client_platform": "ios",
            "p_acquisition": "instagram",
            "p_placement": "profile-link",
            "p_campaign": "presentation-proof-current",
            "p_creative": "ig-feed",
            "p_intent": "presentation",
        },
    )]


@pytest.mark.asyncio
async def test_account_attribution_failure_never_breaks_registration_analytics():
    database = RPCDB(error=RuntimeError("database unavailable"))
    assert await record_account_created_event(
        database,
        user_id="00000000-0000-0000-0000-000000000001",
        request=request_for("www.askcrump.com"),
        acquisition="instagram",
    ) is False


class RegistrationDB:
    def __init__(self) -> None:
        self.inserted_user: dict | None = None

    async def select_one(self, table, **kwargs):
        return None

    async def insert(self, table, payload):
        self.inserted_user = dict(payload)
        return [dict(payload)]

    async def upsert(self, table, payload, *, on_conflict):
        return [dict(payload)]

    async def update(self, *args, **kwargs):
        return []


class VerificationEmail:
    async def send_verification(self, *args, **kwargs):
        return True


@pytest.mark.asyncio
async def test_registration_records_first_touch_once_on_the_authoritative_event(monkeypatch):
    captured: list[dict] = []
    database = RegistrationDB()

    async def allow_rate_limit(*args, **kwargs):
        return None

    async def capture_account_event(*args, **kwargs):
        captured.append(dict(kwargs))
        return True

    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "email_service", VerificationEmail())
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "hash_password", lambda password: "hashed-password")
    monkeypatch.setattr(auth_routes, "record_account_created_event", capture_account_event)

    result = await auth_routes.register(
        RegisterRequest(
            email="campaign-fixture@example.com",
            password="StrongPass1",
            source="instagram",
            placement="profile-link",
            campaign="presentation-proof-current",
            creative="ig-feed",
            intent="presentation",
        ),
        request_for("www.askcrump.com"),
    )

    assert result["success"] is True
    assert database.inserted_user["registration_environment"] == "production"
    assert len(captured) == 1
    assert captured[0] == {
        "user_id": captured[0]["user_id"],
        "request": captured[0]["request"],
        "acquisition": "instagram",
        "placement": "profile-link",
        "campaign": "presentation-proof-current",
        "creative": "ig-feed",
        "intent": "presentation",
    }


def test_registration_rejects_overlength_attribution_values():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="invalid@example.com",
            password="StrongPass1",
            campaign="x" * 33,
        )


def test_browser_contract_carries_only_the_bounded_first_touch_tuple():
    landing = (ROOT / "public" / "landing.js").read_text(encoding="utf-8")
    controller = (ROOT / "public" / "auth-controller.js").read_text(encoding="utf-8")
    controller_attribution = controller[
        controller.index("const FIRST_TOUCH_KEY"):
        controller.index("function trackFunnel")
    ]

    for source in (landing, controller_attribution):
        assert "askcrump.first-touch-attribution" in source
        assert "FIRST_TOUCH_TTL_MS = 24 * 60 * 60 * 1000" in source
        assert "presentation-proof-current" in source
        assert "real-product-continuity" in source
        assert "project-memory-boundaries" in source
        assert "creator-cohort-01" in source
        assert "const attribution = stored ? normalizeAttribution(stored) : candidate" in source
        assert "stored.placement || candidate.placement" not in source
        assert "stored.campaign || candidate.campaign" not in source
        assert "prompt:" not in source
        assert "email:" not in source
        assert "referrer:" not in source

    assert "destination.searchParams.set('campaign', attribution.campaign)" in landing
    assert "destination.searchParams.set('creative', attribution.creative)" in landing
    assert "campaign: attribution.campaign" in controller
    assert "creative: attribution.creative" in controller
    assert "intent: attribution.intent" in controller


def test_weekly_export_is_private_content_free_and_has_explicit_denominators():
    migration = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(migration.lower().split())
    return_contract = normalized[
        normalized.index("returns table", normalized.index("product_weekly_attribution_export")):
        normalized.index("language plpgsql", normalized.index("product_weekly_attribution_export"))
    ]

    assert "product_weekly_attribution_export" in normalized
    assert "security invoker" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "to service_role" in normalized
    assert "activation_eligible_24h" in return_contract
    assert "durable_value_eligible_24h" in return_contract
    assert "d1_eligible" in return_contract
    assert "d7_eligible" in return_contract
    assert "paid_conversion_eligible" in return_contract
    assert "recognized_revenue_cents bigint" in return_contract
    assert "null::bigint" in normalized
    assert "user_id" not in return_contract
    assert "email" not in return_contract
    assert "prompt" not in return_contract
    assert "filename" not in return_contract
    assert "metadata jsonb" not in normalized
    assert "on conflict (user_id, event_name, event_key, environment) do nothing" in normalized
    assert "on delete cascade" not in normalized  # inherited from the existing table FK
    assert "u.registration_environment = p_environment" in normalized
    assert "server-derived account-creation environment" in normalized
    assert "f.activation_at is not null" in normalized
    assert "coalesce(f.activation_at, f.cohort_at)" not in normalized
    assert "d1 and d7 use activated-user denominators" in normalized
    assert "campaign = 'real-product-continuity'" in normalized
    assert "v_campaign = 'real-product-continuity'" in normalized
    assert "campaign = 'rough-idea-launch-plan' and source = 'organic-search'" in normalized
    assert "v_campaign = 'rough-idea-launch-plan' and v_acquisition = 'organic-search'" in normalized
