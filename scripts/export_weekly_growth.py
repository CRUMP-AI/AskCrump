"""Export Ask Crump's privacy-safe weekly growth evidence as aggregate JSON."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib import error, request


SENSITIVE_KEYS = frozenset({
    "user_id", "account_id", "email", "full_name", "prompt", "response",
    "filename", "file_name", "project_id", "file_id", "chat_id", "message_id",
    "artifact_url", "storage_path", "payment_method", "payment_object",
    "payment_intent", "external_id", "referrer", "url", "ip_address",
    "user_agent", "session_id", "device_id", "metadata",
})


def utc_timestamp(value: str) -> str:
    candidate = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must include a UTC offset.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def optional_count(value: int | None) -> dict[str, Any]:
    if value is None:
        return {"status": "not_provided", "value": None}
    if value < 0:
        raise ValueError("Aggregate counts and monetary values cannot be negative.")
    return {"status": "measured", "value": value}


def percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator * 100.0 / denominator, 1)


def cents_per_account(cents: int | None, accounts: int) -> int | None:
    if cents is None or accounts <= 0:
        return None
    return round(cents / accounts)


def sum_field(rows: list[dict[str, Any]], field: str) -> int:
    return sum(int(row.get(field) or 0) for row in rows)


def ensure_aggregate_rows(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        lowered = {str(key).lower() for key in row}
        exposed = lowered & SENSITIVE_KEYS
        if exposed:
            raise ValueError(
                f"The database export unexpectedly returned sensitive fields: {sorted(exposed)}"
            )


def build_report(
    rows: list[dict[str, Any]],
    *,
    since: str,
    until: str,
    environment: str,
    landing_visitors: int | None = None,
    refund_accounts: int | None = None,
    recognized_revenue_cents: int | None = None,
    refund_adjustments_cents: int | None = None,
    variable_cost_cents: int | None = None,
    ad_spend_cents: int | None = None,
    currency: str = "usd",
) -> dict[str, Any]:
    ensure_aggregate_rows(rows)
    period_since = utc_timestamp(since)
    period_until = utc_timestamp(until)
    since_instant = datetime.fromisoformat(period_since.replace("Z", "+00:00"))
    until_instant = datetime.fromisoformat(period_until.replace("Z", "+00:00"))
    if since_instant >= until_instant:
        raise ValueError("The export requires a valid half-open reporting window.")
    if environment not in {"production", "preview", "development"}:
        raise ValueError("Invalid reporting environment.")
    normalized_currency = currency.strip().lower()
    if not normalized_currency.isalpha() or len(normalized_currency) != 3:
        raise ValueError("Currency must be a three-letter code such as usd.")

    supplied = {
        "landing_visitors": landing_visitors,
        "refund_accounts": refund_accounts,
        "recognized_revenue_cents": recognized_revenue_cents,
        "refund_adjustments_cents": refund_adjustments_cents,
        "variable_cost_cents": variable_cost_cents,
        "ad_spend_cents": ad_spend_cents,
    }
    evidence = {key: optional_count(value) for key, value in supplied.items()}

    accounts = sum_field(rows, "accounts_created")
    activation = sum_field(rows, "activation_reached_24h")
    useful_feedback = sum_field(rows, "useful_feedback_reached_24h")
    durable_value = sum_field(rows, "durable_value_reached_24h")
    decision_grade_value = sum_field(rows, "decision_grade_value_reached_24h")
    project_value = sum_field(rows, "project_created_reached_24h")
    project_file_value = sum_field(rows, "project_file_reached_24h")
    ready_file_value = sum_field(rows, "ready_file_reached_24h")
    d1_eligible = sum_field(rows, "d1_eligible")
    d1_returned = sum_field(rows, "d1_returned")
    d7_eligible = sum_field(rows, "d7_eligible")
    d7_returned = sum_field(rows, "d7_returned")
    payers = sum_field(rows, "distinct_payers")
    payer_eligible = sum_field(rows, "paid_conversion_eligible")

    net_revenue = None
    if recognized_revenue_cents is not None and refund_adjustments_cents is not None:
        net_revenue = recognized_revenue_cents - refund_adjustments_cents

    return {
        "schema": "ask-crump.weekly-growth.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window": {
            "since": period_since,
            "until": period_until,
            "boundary": "half-open",
            "environment": environment,
        },
        "privacy": {
            "aggregate_only": True,
            "contains_customer_content": False,
            "contains_account_identifiers": False,
        },
        "cohorts": rows,
        "authoritative_period_totals": {
            "currency": normalized_currency,
            **evidence,
            "net_recognized_revenue_cents": {
                "status": "measured" if net_revenue is not None else "not_provided",
                "value": net_revenue,
            },
        },
        "derived_rates": {
            "landing_to_signup_pct": percentage(accounts, landing_visitors or 0),
            "signup_to_activation_24h_pct": percentage(activation, accounts),
            "signup_to_useful_feedback_24h_pct": percentage(useful_feedback, accounts),
            "signup_to_durable_value_24h_pct": percentage(durable_value, accounts),
            "signup_to_decision_grade_value_24h_pct": percentage(
                decision_grade_value,
                accounts,
            ),
            "signup_to_project_24h_pct": percentage(project_value, accounts),
            "signup_to_project_file_24h_pct": percentage(project_file_value, accounts),
            "signup_to_ready_file_24h_pct": percentage(ready_file_value, accounts),
            "d1_retention_pct": percentage(d1_returned, d1_eligible),
            "d7_retention_pct": percentage(d7_returned, d7_eligible),
            "paid_conversion_pct": percentage(payers, payer_eligible),
            "cost_per_activated_user_cents": cents_per_account(ad_spend_cents, activation),
            "cost_per_decision_grade_user_cents": cents_per_account(
                ad_spend_cents,
                decision_grade_value,
            ),
            "cost_per_d7_retained_user_cents": cents_per_account(ad_spend_cents, d7_returned),
        },
        "reconciliation": {
            "anonymous_boundary": (
                "Landing visitors are aggregate, cross-system directional evidence and are not "
                "silently merged into server-authoritative account cohorts."
            ),
            "payer_boundary": (
                "Checkout events are diagnostics, not payers. Payer counts require an active "
                "provider-backed subscription or provider-backed credit-purchase ledger row."
            ),
            "finance_boundary": (
                "Revenue, refunds, variable cost, and spend remain not_provided until an "
                "authorized finance source supplies aggregate period totals."
            ),
        },
    }


def fetch_rows(
    *,
    supabase_url: str,
    service_key: str,
    since: str,
    until: str,
    environment: str,
    include_internal: bool,
) -> list[dict[str, Any]]:
    endpoint = f"{supabase_url.rstrip('/')}/rest/v1/rpc/product_weekly_attribution_export"
    body = json.dumps({
        "p_since": utc_timestamp(since),
        "p_until": utc_timestamp(until),
        "p_environment": environment,
        "p_include_internal": include_internal,
    }).encode("utf-8")
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
        raise RuntimeError(f"Supabase export failed with HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError("Supabase export could not be reached.") from exc
    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
        raise RuntimeError("Supabase returned an unexpected weekly export shape.")
    return result


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
        rows = fetch_rows(
            supabase_url=supabase_url,
            service_key=service_key,
            since=args.since,
            until=args.until,
            environment=args.environment,
            include_internal=args.include_internal,
        )
        report = build_report(
            rows,
            since=args.since,
            until=args.until,
            environment=args.environment,
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
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
