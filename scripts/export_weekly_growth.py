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
from urllib.parse import urlsplit


SENSITIVE_KEYS = frozenset({
    "user_id", "account_id", "email", "full_name", "prompt", "response",
    "filename", "file_name", "project_id", "file_id", "chat_id", "message_id",
    "artifact_url", "storage_path", "payment_method", "payment_object",
    "payment_intent", "external_id", "referrer", "url", "ip_address",
    "user_agent", "session_id", "device_id", "metadata",
})

COUNT_FIELDS = (
    "accounts_created",
    "account_event_recorded",
    "verified_now",
    "workspace_opened",
    "activation_eligible_24h",
    "activation_reached_24h",
    "useful_feedback_reached_24h",
    "durable_value_eligible_24h",
    "durable_value_reached_24h",
    "decision_grade_value_reached_24h",
    "project_created_reached_24h",
    "project_file_reached_24h",
    "ready_file_reached_24h",
    "d1_eligible",
    "d1_returned",
    "d7_eligible",
    "d7_returned",
    "plan_intent_reached",
    "subscription_checkout_opened",
    "subscription_checkout_completed",
    "credit_checkout_opened",
    "credit_checkout_completed",
    "distinct_payers",
    "paid_conversion_eligible",
    "active_paid_now",
)

OPTIONAL_DATABASE_TOTAL_FIELDS = (
    "refund_accounts",
    "recognized_revenue_cents",
    "variable_cost_cents",
)

COUNT_RELATIONSHIPS = (
    ("account_event_recorded", "accounts_created"),
    ("verified_now", "accounts_created"),
    ("workspace_opened", "accounts_created"),
    ("activation_eligible_24h", "accounts_created"),
    ("activation_reached_24h", "activation_eligible_24h"),
    ("useful_feedback_reached_24h", "activation_eligible_24h"),
    ("durable_value_eligible_24h", "accounts_created"),
    ("durable_value_reached_24h", "durable_value_eligible_24h"),
    ("decision_grade_value_reached_24h", "activation_reached_24h"),
    ("project_created_reached_24h", "durable_value_eligible_24h"),
    ("project_file_reached_24h", "durable_value_eligible_24h"),
    ("ready_file_reached_24h", "durable_value_eligible_24h"),
    ("d1_eligible", "accounts_created"),
    ("d1_returned", "d1_eligible"),
    ("d7_eligible", "d1_eligible"),
    ("d7_returned", "d7_eligible"),
    ("plan_intent_reached", "accounts_created"),
    ("subscription_checkout_opened", "accounts_created"),
    ("subscription_checkout_completed", "accounts_created"),
    ("credit_checkout_opened", "accounts_created"),
    ("credit_checkout_completed", "accounts_created"),
    ("distinct_payers", "accounts_created"),
    ("paid_conversion_eligible", "accounts_created"),
    ("active_paid_now", "distinct_payers"),
)

EXPECTED_SUPABASE_HOST = "xncftwjfpjskgtwgbgci.supabase.co"
VALID_ENVIRONMENTS = frozenset({"production", "preview", "development"})


def utc_timestamp(value: str) -> str:
    candidate = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must include a UTC offset.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validated_window(*, since: str, until: str, environment: str) -> tuple[str, str]:
    """Validate and normalize the reporting boundary before any RPC is attempted."""
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
    """Return Ask Crump's exact Supabase origin before any secret is attached."""
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


def optional_count(value: int | None) -> dict[str, Any]:
    if value is None:
        return {"status": "not_provided", "value": None}
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("Aggregate counts and monetary values must be nonnegative integers.")
    return {"status": "measured", "value": value}


def percentage(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator * 100.0 / denominator, 1)


def cents_per_account(cents: int | None, accounts: int) -> int | None:
    if cents is None or accounts <= 0:
        return None
    return round(cents / accounts)


def validated_count(row: dict[str, Any], field: str, row_index: int) -> int:
    if field not in row:
        raise ValueError(f"Weekly cohort row {row_index} is missing required count {field}.")
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(
            f"Weekly cohort row {row_index} has invalid nonnegative integer count {field}."
        )
    return value


def sum_field(rows: list[dict[str, Any]], field: str) -> int:
    return sum(validated_count(row, field, index) for index, row in enumerate(rows))


def ensure_aggregate_rows(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        lowered = {str(key).lower() for key in row}
        exposed = lowered & SENSITIVE_KEYS
        if exposed:
            raise ValueError(
                f"The database export unexpectedly returned sensitive fields: {sorted(exposed)}"
            )


def validate_weekly_cohorts(
    rows: list[dict[str, Any]],
    *,
    period_since: str,
    period_until: str,
) -> None:
    """Reject impossible or mismatched aggregate evidence before calculating rates."""
    expected_since = datetime.fromisoformat(period_since.replace("Z", "+00:00"))
    expected_until = datetime.fromisoformat(period_until.replace("Z", "+00:00"))
    shared_boundary: tuple[str, str] | None = None

    for index, row in enumerate(rows):
        counts = {field: validated_count(row, field, index) for field in COUNT_FIELDS}
        for field in OPTIONAL_DATABASE_TOTAL_FIELDS:
            value = row.get(field)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(
                    f"Weekly cohort row {index} has invalid optional total {field}."
                )

        try:
            cohort_since = utc_timestamp(str(row["cohort_since"]))
            cohort_until = utc_timestamp(str(row["cohort_until"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Weekly cohort row {index} has an invalid cohort boundary."
            ) from exc
        boundary = (cohort_since, cohort_until)
        if shared_boundary is None:
            shared_boundary = boundary
        elif boundary != shared_boundary:
            raise ValueError("Weekly cohort rows have inconsistent cohort boundaries.")

        cohort_since_instant = datetime.fromisoformat(cohort_since.replace("Z", "+00:00"))
        cohort_until_instant = datetime.fromisoformat(cohort_until.replace("Z", "+00:00"))
        if cohort_since_instant < expected_since or cohort_since_instant >= expected_until:
            raise ValueError("Weekly cohort start falls outside the requested reporting window.")
        if cohort_until_instant != expected_until:
            raise ValueError("Weekly cohort end does not match the requested reporting window.")

        for numerator, denominator in COUNT_RELATIONSHIPS:
            if counts[numerator] > counts[denominator]:
                raise ValueError(
                    f"Weekly cohort row {index} reports {numerator} above {denominator}."
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
    period_since, period_until = validated_window(
        since=since,
        until=until,
        environment=environment,
    )
    validate_weekly_cohorts(
        rows,
        period_since=period_since,
        period_until=period_until,
    )
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
    origin = validated_supabase_url(supabase_url)
    period_since, period_until = validated_window(
        since=since,
        until=until,
        environment=environment,
    )
    endpoint = f"{origin}/rest/v1/rpc/product_weekly_attribution_export"
    body = json.dumps({
        "p_since": period_since,
        "p_until": period_until,
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
