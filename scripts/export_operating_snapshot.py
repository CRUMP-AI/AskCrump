"""Export one privacy-safe Ask Crump operating snapshot from protected aggregate RPCs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
from urllib import error, request
from urllib.parse import urlsplit

if __package__:
    from .export_weekly_growth import (
        build_report,
        ensure_aggregate_rows,
        sum_field,
        utc_timestamp,
    )
else:
    from export_weekly_growth import (  # type: ignore[import-not-found]
        build_report,
        ensure_aggregate_rows,
        sum_field,
        utc_timestamp,
    )


COMMON_RPCS = (
    "product_growth_funnel_snapshot",
    "product_weekly_attribution_export",
    "product_artifact_journey_snapshot",
    "product_project_continuity_snapshot",
    "product_plan_conversion_snapshot",
    "product_outcome_issue_snapshot",
    "product_navigation_discovery_snapshot",
)
PRODUCTION_ONLY_RPCS = ("product_project_limit_plan_snapshot",)
WINDOW_RPCS = ("product_weekly_lifecycle_export",)
STATE_RPCS = ("demo_recording_proof_snapshot",)
TRANSIENT_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})
VALID_ENVIRONMENTS = frozenset({"production", "preview", "development"})
EXPECTED_SUPABASE_HOST = "xncftwjfpjskgtwgbgci.supabase.co"
RpcFetcher = Callable[[str, dict[str, Any]], list[dict[str, Any]]]


def validated_window(*, since: str, until: str, environment: str) -> tuple[str, str]:
    period_since = utc_timestamp(since)
    period_until = utc_timestamp(until)
    since_instant = datetime.fromisoformat(period_since.replace("Z", "+00:00"))
    until_instant = datetime.fromisoformat(period_until.replace("Z", "+00:00"))
    if since_instant >= until_instant:
        raise ValueError("The export requires a valid half-open reporting window.")
    if environment not in VALID_ENVIRONMENTS:
        raise ValueError("Invalid reporting environment.")
    return period_since, period_until


def validated_supabase_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or parsed.hostname != EXPECTED_SUPABASE_HOST
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "SUPABASE_URL must be Ask Crump's exact HTTPS Supabase project origin."
        )
    return f"https://{EXPECTED_SUPABASE_HOST}"


def rpc_payloads(
    *,
    since: str,
    until: str,
    environment: str,
    include_internal: bool,
) -> dict[str, dict[str, Any]]:
    period_since, period_until = validated_window(
        since=since,
        until=until,
        environment=environment,
    )
    common = {
        "p_since": period_since,
        "p_until": period_until,
        "p_environment": environment,
        "p_include_internal": include_internal,
    }
    payloads = {name: dict(common) for name in COMMON_RPCS}
    payloads.update({
        name: {
            "p_since": period_since,
            "p_until": period_until,
            "p_environment": environment,
        }
        for name in WINDOW_RPCS
    })
    if environment == "production":
        payloads.update({
            name: {
                "p_since": period_since,
                "p_until": period_until,
                "p_environment": environment,
            }
            for name in PRODUCTION_ONLY_RPCS
        })
    payloads.update({name: {} for name in STATE_RPCS})
    return payloads


def fetch_rpc_rows(
    *,
    supabase_url: str,
    service_key: str,
    rpc_name: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    origin = validated_supabase_url(supabase_url)
    endpoint = f"{origin}/rest/v1/rpc/{rpc_name}"
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        call = request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "apikey": service_key,
                "authorization": f"Bearer {service_key}",
                "content-type": "application/json",
            },
        )
        try:
            with request.urlopen(call, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            last_error = exc
            if exc.code not in TRANSIENT_HTTP_STATUS or attempt == 3:
                raise RuntimeError(f"{rpc_name} failed with HTTP {exc.code}.") from exc
        except error.URLError as exc:
            last_error = exc
            if attempt == 3:
                raise RuntimeError(f"{rpc_name} could not be reached.") from exc
        else:
            if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
                raise RuntimeError(f"{rpc_name} returned an unexpected aggregate shape.")
            ensure_aggregate_rows(result)
            return result
        time.sleep(attempt * 0.25)
    raise RuntimeError(f"{rpc_name} did not return a result.") from last_error


def collect_rpc_rows(
    fetcher: RpcFetcher,
    *,
    since: str,
    until: str,
    environment: str,
    include_internal: bool,
) -> dict[str, list[dict[str, Any]]]:
    payloads = rpc_payloads(
        since=since,
        until=until,
        environment=environment,
        include_internal=include_internal,
    )
    sections: dict[str, list[dict[str, Any]]] = {}
    for rpc_name, payload in payloads.items():
        rows = fetcher(rpc_name, payload)
        ensure_aggregate_rows(rows)
        sections[rpc_name] = rows
    return sections


def build_operating_snapshot(
    sections: dict[str, list[dict[str, Any]]],
    *,
    since: str,
    until: str,
    environment: str,
    include_internal: bool,
    landing_visitors: int | None = None,
    refund_accounts: int | None = None,
    recognized_revenue_cents: int | None = None,
    refund_adjustments_cents: int | None = None,
    variable_cost_cents: int | None = None,
    ad_spend_cents: int | None = None,
    currency: str = "usd",
) -> dict[str, Any]:
    expected = set(rpc_payloads(
        since=since,
        until=until,
        environment=environment,
        include_internal=include_internal,
    ))
    if set(sections) != expected:
        missing = sorted(expected - set(sections))
        unexpected = sorted(set(sections) - expected)
        raise ValueError(
            f"Operating snapshot sections are incomplete. Missing: {missing}; unexpected: {unexpected}."
        )
    for rows in sections.values():
        ensure_aggregate_rows(rows)

    weekly_rows = sections["product_weekly_attribution_export"]
    weekly = build_report(
        weekly_rows,
        since=since,
        until=until,
        environment=environment,
        landing_visitors=landing_visitors,
        refund_accounts=refund_accounts,
        recognized_revenue_cents=recognized_revenue_cents,
        refund_adjustments_cents=refund_adjustments_cents,
        variable_cost_cents=variable_cost_cents,
        ad_spend_cents=ad_spend_cents,
        currency=currency,
    )
    d1_eligible = sum_field(weekly_rows, "d1_eligible")
    d1_returned = sum_field(weekly_rows, "d1_returned")
    d7_eligible = sum_field(weekly_rows, "d7_eligible")
    d7_returned = sum_field(weekly_rows, "d7_returned")

    return {
        "schema": "ask-crump.operating-snapshot.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window": weekly["window"],
        "privacy": {
            "aggregate_only": True,
            "contains_customer_content": False,
            "contains_account_identifiers": False,
            "service_role_required": True,
            "internal_accounts_included": include_internal,
        },
        "retention_readiness": {
            "d1": {
                "status": "eligible" if d1_eligible else "not_yet_eligible",
                "eligible_accounts": d1_eligible,
                "returned_accounts": d1_returned,
                "rate_pct": weekly["derived_rates"]["d1_retention_pct"],
            },
            "d7": {
                "status": "eligible" if d7_eligible else "not_yet_eligible",
                "eligible_accounts": d7_eligible,
                "returned_accounts": d7_returned,
                "rate_pct": weekly["derived_rates"]["d7_retention_pct"],
            },
        },
        "weekly_growth": weekly,
        "sections": sections,
        "boundaries": {
            "all_sections_required": True,
            "lifecycle_export_excludes_internal_accounts_by_database_contract": True,
            "project_limit_experiment_is_production_only": True,
            "demo_proof_is_boolean_state_only": True,
            "no_database_writes": True,
        },
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--since", required=True, help="UTC-inclusive cohort start")
    cli.add_argument("--until", default=datetime.now(timezone.utc).isoformat(), help="UTC-exclusive cohort end")
    cli.add_argument("--environment", choices=("production", "preview", "development"), default="production")
    cli.add_argument("--include-internal", action="store_true")
    cli.add_argument("--landing-visitors", type=int)
    cli.add_argument("--refund-accounts", type=int)
    cli.add_argument("--recognized-revenue-cents", type=int)
    cli.add_argument("--refund-adjustments-cents", type=int)
    cli.add_argument("--variable-cost-cents", type=int)
    cli.add_argument("--ad-spend-cents", type=int)
    cli.add_argument("--currency", default="usd")
    cli.add_argument("--output", type=Path)
    return cli


def main() -> int:
    args = parser().parse_args()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not supabase_url or not service_key:
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY are required.", file=sys.stderr)
        return 2
    try:
        sections = collect_rpc_rows(
            lambda name, payload: fetch_rpc_rows(
                supabase_url=supabase_url,
                service_key=service_key,
                rpc_name=name,
                payload=payload,
            ),
            since=args.since,
            until=args.until,
            environment=args.environment,
            include_internal=args.include_internal,
        )
        report = build_operating_snapshot(
            sections,
            since=args.since,
            until=args.until,
            environment=args.environment,
            include_internal=args.include_internal,
            landing_visitors=args.landing_visitors,
            refund_accounts=args.refund_accounts,
            recognized_revenue_cents=args.recognized_revenue_cents,
            refund_adjustments_cents=args.refund_adjustments_cents,
            variable_cost_cents=args.variable_cost_cents,
            ad_spend_cents=args.ad_spend_cents,
            currency=args.currency,
        )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(args.output)
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
