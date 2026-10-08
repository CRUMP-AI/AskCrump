"""Export one privacy-safe Ask Crump operating snapshot from protected aggregate RPCs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
from urllib import error, request

if __package__:
    from .export_weekly_growth import (
        EXPECTED_SUPABASE_HOST as EXPECTED_SUPABASE_HOST,
        build_report,
        ensure_aggregate_rows,
        sum_field,
        utc_timestamp,
        validated_supabase_url,
        validated_window,
    )
else:
    from export_weekly_growth import (  # type: ignore[import-not-found]
        EXPECTED_SUPABASE_HOST as EXPECTED_SUPABASE_HOST,
        build_report,
        ensure_aggregate_rows,
        sum_field,
        utc_timestamp,
        validated_supabase_url,
        validated_window,
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
NAVIGATION_DESTINATIONS = (
    "ask",
    "chats",
    "projects",
    "create",
    "video",
    "library",
    "you",
    "intelligence",
    "code",
)
GROWTH_FUNNEL_METRICS = (
    "accounts_created",
    "account_event_recorded",
    "verified_now",
    "optional_profile_completed",
    "workspace_opened",
    "starter_intent_reached",
    "activation_reached",
    "outcome_confirmed_useful",
    "outcome_reported_needs_work",
    "durable_value_reached",
    "recent_work_resumed",
    "response_shared",
    "plan_intent_reached",
    "checkout_opened",
    "checkout_completed",
    "active_paid_now",
    "d1_returned",
    "d7_returned",
)
GROWTH_FUNNEL_FIELDS = frozenset({
    "stage_order",
    "metric",
    "accounts",
    "eligible",
    "rate_pct",
})
GROWTH_FUNNEL_COHORT_ELIGIBLE_METRICS = frozenset({
    "accounts_created",
    "account_event_recorded",
    "verified_now",
    "optional_profile_completed",
    "workspace_opened",
    "starter_intent_reached",
    "activation_reached",
    "durable_value_reached",
    "recent_work_resumed",
    "response_shared",
    "plan_intent_reached",
    "checkout_opened",
    "checkout_completed",
    "active_paid_now",
})
ARTIFACT_JOURNEY_TYPES = frozenset({
    "document",
    "image",
    "video",
    "manuscript",
    "code",
    "spreadsheet",
    "presentation",
    "pdf",
    "project",
    "file",
})
ARTIFACT_JOURNEY_COUNT_FIELDS = (
    "requested",
    "packaged",
    "packaging_failed",
    "downloaded",
)
ARTIFACT_JOURNEY_RATE_FIELDS = (
    ("request_to_package_rate_pct", "packaged", "requested"),
    ("package_to_download_rate_pct", "downloaded", "packaged"),
)
ARTIFACT_JOURNEY_FIELDS = frozenset(
    ("artifact_type",)
    + ARTIFACT_JOURNEY_COUNT_FIELDS
    + tuple(field for field, _numerator, _denominator in ARTIFACT_JOURNEY_RATE_FIELDS)
)
PROJECT_CONTINUITY_COUNT_FIELDS = (
    "accounts_created",
    "activation_reached",
    "project_save_offer_shown",
    "project_save_offer_to_intent",
    "project_save_offer_without_later_intent",
    "project_save_intent_without_prior_offer",
    "project_save_intent_reached",
    "project_save_completed",
    "project_save_paired_completion",
    "project_save_intent_without_completion",
    "project_save_completion_without_intent",
    "project_resumed_after_save",
)
PROJECT_CONTINUITY_ATTRIBUTION_FIELDS = (
    "acquisition",
    "placement",
    "campaign",
    "creative",
    "intent",
)
PROJECT_CONTINUITY_BOUNDARY_FIELDS = (
    "cohort_since",
    "cohort_until",
    "offer_measurement_since",
)
PROJECT_CONTINUITY_RATE_FIELDS = (
    (
        "offer_to_intent_rate_pct",
        "project_save_offer_to_intent",
        "project_save_offer_shown",
    ),
    (
        "intent_to_completion_rate_pct",
        "project_save_paired_completion",
        "project_save_intent_reached",
    ),
    (
        "completion_to_resume_rate_pct",
        "project_resumed_after_save",
        "project_save_completed",
    ),
)
PROJECT_CONTINUITY_FIELDS = frozenset(
    PROJECT_CONTINUITY_BOUNDARY_FIELDS
    + PROJECT_CONTINUITY_ATTRIBUTION_FIELDS
    + PROJECT_CONTINUITY_COUNT_FIELDS
    + tuple(field for field, _numerator, _denominator in PROJECT_CONTINUITY_RATE_FIELDS)
)
PROJECT_CONTINUITY_COHORT_FLOOR = "2026-08-23T09:10:55.602863Z"
PROJECT_CONTINUITY_OFFER_MEASUREMENT_SINCE = "2026-09-14T18:34:14Z"
RpcFetcher = Callable[[str, dict[str, Any]], list[dict[str, Any]]]


class _RejectRedirects(request.HTTPRedirectHandler):
    """Keep privileged Supabase headers on the validated project origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise error.HTTPError(
            req.full_url,
            code,
            "Privileged Supabase RPC redirects are forbidden.",
            headers,
            fp,
        )


RPC_OPENER = request.build_opener(_RejectRedirects())


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
        headers = {
            "apikey": service_key,
            "content-type": "application/json",
        }
        if not service_key.startswith("sb_secret_"):
            headers["authorization"] = f"Bearer {service_key}"
        call = request.Request(
            endpoint,
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            with RPC_OPENER.open(call, timeout=30) as response:
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


def _growth_funnel_count(
    row: dict[str, Any],
    *,
    row_index: int,
    field: str,
) -> int:
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(
            f"Growth funnel row {row_index} has invalid nonnegative integer count {field}."
        )
    return value


def _growth_funnel_rate(
    row: dict[str, Any],
    *,
    row_index: int,
    accounts: int,
    eligible: int,
) -> None:
    observed = row["rate_pct"]
    if eligible == 0:
        if observed is not None:
            raise ValueError(
                f"Growth funnel row {row_index} rate must be unavailable "
                "with a zero denominator."
            )
        return
    if not isinstance(observed, (int, float)) or isinstance(observed, bool):
        raise ValueError(
            f"Growth funnel row {row_index} has an invalid numeric rate."
        )
    try:
        observed_decimal = Decimal(str(observed))
    except InvalidOperation as exc:
        raise ValueError(
            f"Growth funnel row {row_index} has an invalid numeric rate."
        ) from exc
    if not observed_decimal.is_finite():
        raise ValueError(
            f"Growth funnel row {row_index} has an invalid numeric rate."
        )
    expected = (
        Decimal(100) * Decimal(accounts) / Decimal(eligible)
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if observed_decimal != expected:
        raise ValueError(
            f"Growth funnel row {row_index} rate does not match its exact denominator."
        )


def validate_growth_funnel(rows: list[dict[str, Any]]) -> None:
    """Reject malformed company-funnel evidence before it reaches operators."""
    ensure_aggregate_rows(rows)
    if len(rows) != len(GROWTH_FUNNEL_METRICS):
        raise ValueError("Growth funnel must contain the 18 fixed stages exactly once.")

    observed: dict[str, tuple[int, int]] = {}
    for index, (row, expected_metric) in enumerate(
        zip(rows, GROWTH_FUNNEL_METRICS, strict=True),
        start=1,
    ):
        observed_fields = {str(field) for field in row}
        if observed_fields != GROWTH_FUNNEL_FIELDS:
            missing = sorted(GROWTH_FUNNEL_FIELDS - observed_fields)
            unexpected = sorted(observed_fields - GROWTH_FUNNEL_FIELDS)
            raise ValueError(
                f"Growth funnel row {index - 1} schema drifted. "
                f"Missing: {missing}; unexpected: {unexpected}."
            )
        if (
            not isinstance(row["stage_order"], int)
            or isinstance(row["stage_order"], bool)
            or row["stage_order"] != index
        ):
            raise ValueError("Growth funnel stages are not in canonical order.")
        if row["metric"] != expected_metric:
            raise ValueError("Growth funnel metrics are not in canonical order.")

        accounts = _growth_funnel_count(
            row,
            row_index=index - 1,
            field="accounts",
        )
        eligible = _growth_funnel_count(
            row,
            row_index=index - 1,
            field="eligible",
        )
        if accounts > eligible:
            raise ValueError(
                f"Growth funnel row {index - 1} reports accounts above eligible."
            )
        _growth_funnel_rate(
            row,
            row_index=index - 1,
            accounts=accounts,
            eligible=eligible,
        )
        observed[expected_metric] = (accounts, eligible)

    cohort_accounts = observed["accounts_created"][0]
    if observed["accounts_created"][1] != cohort_accounts:
        raise ValueError("Growth funnel accounts_created must use itself as denominator.")
    for metric in GROWTH_FUNNEL_COHORT_ELIGIBLE_METRICS - {"accounts_created"}:
        if observed[metric][1] != cohort_accounts:
            raise ValueError(
                f"Growth funnel metric {metric} must use accounts_created as denominator."
            )

    activation_accounts = observed["activation_reached"][0]
    for metric in ("outcome_confirmed_useful", "outcome_reported_needs_work"):
        if observed[metric][1] != activation_accounts:
            raise ValueError(
                f"Growth funnel metric {metric} must use activation_reached as denominator."
            )

    d1_eligible = observed["d1_returned"][1]
    d7_eligible = observed["d7_returned"][1]
    if d1_eligible > activation_accounts or d7_eligible > activation_accounts:
        raise ValueError(
            "Growth funnel retention eligibility cannot exceed activated accounts."
        )
    if d7_eligible > d1_eligible:
        raise ValueError(
            "Growth funnel D7 eligibility cannot exceed D1 eligibility."
        )


def validate_growth_attribution_consistency(
    growth_rows: list[dict[str, Any]],
    weekly_rows: list[dict[str, Any]],
) -> None:
    """Reject aggregate sections that disagree on their shared cohort facts."""
    growth = {
        row["metric"]: (row["accounts"], row["eligible"])
        for row in growth_rows
    }
    shared_account_fields = (
        ("accounts_created", "accounts_created"),
        ("account_event_recorded", "account_event_recorded"),
        ("verified_now", "verified_now"),
        ("workspace_opened", "workspace_opened"),
        ("plan_intent_reached", "plan_intent_reached"),
        ("checkout_opened", "subscription_checkout_opened"),
        ("checkout_completed", "subscription_checkout_completed"),
    )
    for growth_metric, weekly_field in shared_account_fields:
        weekly_total = sum_field(weekly_rows, weekly_field)
        if growth[growth_metric][0] != weekly_total:
            raise ValueError(
                f"Growth funnel {growth_metric} conflicts with weekly attribution totals."
            )

    for metric in ("d1_returned", "d7_returned"):
        weekly_accounts = sum_field(weekly_rows, metric)
        weekly_eligible = sum_field(weekly_rows, metric.replace("returned", "eligible"))
        if growth[metric] != (weekly_accounts, weekly_eligible):
            raise ValueError(
                f"Growth funnel {metric} conflicts with weekly attribution totals."
            )


def _artifact_journey_count(
    row: dict[str, Any],
    *,
    row_index: int,
    field: str,
) -> int:
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(
            f"Artifact journey row {row_index} has invalid nonnegative integer count {field}."
        )
    return value


def _artifact_journey_rate(
    row: dict[str, Any],
    *,
    row_index: int,
    field: str,
    numerator: int,
    denominator: int,
) -> None:
    observed = row[field]
    if denominator == 0:
        if observed is not None:
            raise ValueError(
                f"Artifact journey row {row_index} rate {field} must be unavailable "
                "with a zero denominator."
            )
        return
    if not isinstance(observed, (int, float)) or isinstance(observed, bool):
        raise ValueError(
            f"Artifact journey row {row_index} has invalid numeric rate {field}."
        )
    try:
        observed_decimal = Decimal(str(observed))
    except InvalidOperation as exc:
        raise ValueError(
            f"Artifact journey row {row_index} has invalid numeric rate {field}."
        ) from exc
    if not observed_decimal.is_finite():
        raise ValueError(
            f"Artifact journey row {row_index} has invalid numeric rate {field}."
        )
    expected = (
        Decimal(100) * Decimal(numerator) / Decimal(denominator)
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if observed_decimal != expected:
        raise ValueError(
            f"Artifact journey row {row_index} rate {field} does not match "
            "its exact denominator."
        )


def validate_artifact_journey(rows: list[dict[str, Any]]) -> None:
    """Reject malformed artifact-delivery evidence before it reaches operators."""
    ensure_aggregate_rows(rows)
    observed_types: list[str] = []

    for index, row in enumerate(rows):
        observed_fields = {str(field) for field in row}
        if observed_fields != ARTIFACT_JOURNEY_FIELDS:
            missing = sorted(ARTIFACT_JOURNEY_FIELDS - observed_fields)
            unexpected = sorted(observed_fields - ARTIFACT_JOURNEY_FIELDS)
            raise ValueError(
                f"Artifact journey row {index} schema drifted. "
                f"Missing: {missing}; unexpected: {unexpected}."
            )

        artifact_type = row["artifact_type"]
        if not isinstance(artifact_type, str) or artifact_type not in ARTIFACT_JOURNEY_TYPES:
            raise ValueError(
                f"Artifact journey row {index} has an invalid artifact type."
            )
        if artifact_type in observed_types:
            raise ValueError("Artifact journey contains a duplicate artifact type.")
        observed_types.append(artifact_type)

        counts = {
            field: _artifact_journey_count(row, row_index=index, field=field)
            for field in ARTIFACT_JOURNEY_COUNT_FIELDS
        }
        if sum(counts.values()) == 0:
            raise ValueError(
                f"Artifact journey row {index} must contain at least one observed event."
            )

        for field, numerator_field, denominator_field in ARTIFACT_JOURNEY_RATE_FIELDS:
            _artifact_journey_rate(
                row,
                row_index=index,
                field=field,
                numerator=counts[numerator_field],
                denominator=counts[denominator_field],
            )

    if observed_types != sorted(observed_types):
        raise ValueError("Artifact journey rows are not in canonical artifact-type order.")


def _project_continuity_count(
    row: dict[str, Any],
    *,
    row_index: int,
    field: str,
) -> int:
    if field not in row:
        raise ValueError(
            f"Project continuity row {row_index} is missing required count {field}."
        )
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(
            f"Project continuity row {row_index} has invalid nonnegative integer count {field}."
        )
    return value


def _project_continuity_rate(
    row: dict[str, Any],
    *,
    row_index: int,
    field: str,
    numerator: int,
    denominator: int,
) -> None:
    if field not in row:
        raise ValueError(
            f"Project continuity row {row_index} is missing required rate {field}."
        )
    observed = row[field]
    if denominator == 0:
        if observed is not None:
            raise ValueError(
                f"Project continuity row {row_index} rate {field} must be unavailable "
                "with a zero denominator."
            )
        return
    if (
        not isinstance(observed, (int, float))
        or isinstance(observed, bool)
    ):
        raise ValueError(
            f"Project continuity row {row_index} has invalid numeric rate {field}."
        )
    try:
        observed_decimal = Decimal(str(observed))
    except InvalidOperation as exc:
        raise ValueError(
            f"Project continuity row {row_index} has invalid numeric rate {field}."
        ) from exc
    if not observed_decimal.is_finite():
        raise ValueError(
            f"Project continuity row {row_index} has invalid numeric rate {field}."
        )
    expected = (
        Decimal(100) * Decimal(numerator) / Decimal(denominator)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if observed_decimal != expected:
        raise ValueError(
            f"Project continuity row {row_index} rate {field} does not match "
            "its exact denominator."
        )


def validate_project_continuity(
    rows: list[dict[str, Any]],
    *,
    period_since: str,
    period_until: str,
) -> None:
    """Reject impossible Project-continuity evidence before it reaches operators."""
    ensure_aggregate_rows(rows)
    expected_since = datetime.fromisoformat(period_since.replace("Z", "+00:00"))
    expected_until = datetime.fromisoformat(period_until.replace("Z", "+00:00"))
    cohort_floor = datetime.fromisoformat(
        PROJECT_CONTINUITY_COHORT_FLOOR.replace("Z", "+00:00")
    )
    expected_cohort_since = max(expected_since, cohort_floor)
    expected_cohort_since_text = (
        expected_cohort_since.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    shared_boundary: tuple[str, str, str] | None = None
    observed_attribution: set[tuple[str | None, ...]] = set()

    for index, row in enumerate(rows):
        observed_fields = {str(field) for field in row}
        if observed_fields != PROJECT_CONTINUITY_FIELDS:
            missing = sorted(PROJECT_CONTINUITY_FIELDS - observed_fields)
            unexpected = sorted(observed_fields - PROJECT_CONTINUITY_FIELDS)
            raise ValueError(
                f"Project continuity row {index} schema drifted. "
                f"Missing: {missing}; unexpected: {unexpected}."
            )
        counts = {
            field: _project_continuity_count(row, row_index=index, field=field)
            for field in PROJECT_CONTINUITY_COUNT_FIELDS
        }
        try:
            boundary = tuple(
                utc_timestamp(str(row[field]))
                for field in PROJECT_CONTINUITY_BOUNDARY_FIELDS
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Project continuity row {index} has an invalid reporting boundary."
            ) from exc
        if shared_boundary is None:
            shared_boundary = boundary
        elif boundary != shared_boundary:
            raise ValueError("Project continuity rows have inconsistent reporting boundaries.")

        if boundary[0] != expected_cohort_since_text:
            raise ValueError(
                "Project continuity cohort start does not match the requested reporting window."
            )
        if boundary[1] != period_until:
            raise ValueError(
                "Project continuity cohort end does not match the requested reporting window."
            )
        if boundary[2] != PROJECT_CONTINUITY_OFFER_MEASUREMENT_SINCE:
            raise ValueError(
                "Project continuity offer measurement boundary is not authoritative."
            )
        if expected_cohort_since >= expected_until:
            raise ValueError(
                "Project continuity returned rows outside its effective cohort window."
            )

        try:
            attribution = tuple(row[field] for field in PROJECT_CONTINUITY_ATTRIBUTION_FIELDS)
        except KeyError as exc:
            raise ValueError(
                f"Project continuity row {index} is missing an attribution field."
            ) from exc
        if any(value is not None and not isinstance(value, str) for value in attribution):
            raise ValueError(
                f"Project continuity row {index} has an invalid attribution tuple."
            )
        if attribution in observed_attribution:
            raise ValueError("Project continuity contains a duplicate attribution tuple.")
        observed_attribution.add(attribution)

        accounts_created = counts["accounts_created"]
        if accounts_created == 0:
            raise ValueError(
                f"Project continuity row {index} must contain at least one account."
            )
        for field, value in counts.items():
            if field != "accounts_created" and value > accounts_created:
                raise ValueError(
                    f"Project continuity row {index} reports {field} above accounts_created."
                )

        if (
            counts["project_save_offer_to_intent"]
            + counts["project_save_offer_without_later_intent"]
            != counts["project_save_offer_shown"]
        ):
            raise ValueError(
                f"Project continuity row {index} has an invalid offer partition."
            )
        if (
            counts["project_save_paired_completion"]
            + counts["project_save_intent_without_completion"]
            != counts["project_save_intent_reached"]
        ):
            raise ValueError(
                f"Project continuity row {index} has an invalid intent partition."
            )
        if (
            counts["project_save_paired_completion"]
            + counts["project_save_completion_without_intent"]
            != counts["project_save_completed"]
        ):
            raise ValueError(
                f"Project continuity row {index} has an invalid completion partition."
            )
        if (
            counts["project_save_offer_to_intent"]
            + counts["project_save_intent_without_prior_offer"]
            > counts["project_save_intent_reached"]
        ):
            raise ValueError(
                f"Project continuity row {index} classifies more comparable intent "
                "than total intent."
            )
        if (
            counts["project_resumed_after_save"]
            > counts["project_save_completed"]
        ):
            raise ValueError(
                f"Project continuity row {index} reports resumed Projects above completions."
            )

        for field, numerator_field, denominator_field in PROJECT_CONTINUITY_RATE_FIELDS:
            _project_continuity_rate(
                row,
                row_index=index,
                field=field,
                numerator=counts[numerator_field],
                denominator=counts[denominator_field],
            )


def validated_navigation_discovery(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate the fixed navigation aggregate before presenting it as evidence."""
    destinations = tuple(row.get("destination") for row in rows)
    if destinations != NAVIGATION_DESTINATIONS:
        raise ValueError(
            "Navigation discovery must contain the nine fixed destinations exactly once and in order."
        )

    shared_fields = ("measurement_since", "window_since", "window_until")
    for field in shared_fields:
        values = {row.get(field) for row in rows}
        if len(values) != 1 or None in values:
            raise ValueError(f"Navigation discovery has an inconsistent {field} boundary.")

    denominators = {row.get("active_workspace_accounts") for row in rows}
    if len(denominators) != 1:
        raise ValueError("Navigation discovery has inconsistent active-account denominators.")
    active_accounts = next(iter(denominators))
    if (
        not isinstance(active_accounts, int)
        or isinstance(active_accounts, bool)
        or active_accounts < 0
    ):
        raise ValueError("Navigation discovery has an invalid active-account denominator.")

    selected_by_destination: dict[str, int] = {}
    selected_days_by_destination: dict[str, int] = {}
    for row in rows:
        destination = row["destination"]
        selected_accounts = row.get("selected_accounts")
        selected_account_days = row.get("selected_account_days")
        rate = row.get("selected_account_rate_pct")
        for field, value in (
            ("selected_accounts", selected_accounts),
            ("selected_account_days", selected_account_days),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"Navigation discovery has an invalid {field} value for {destination}."
                )
        if selected_accounts > active_accounts:
            raise ValueError(
                f"Navigation discovery selected accounts exceed its denominator for {destination}."
            )
        if selected_account_days < selected_accounts:
            raise ValueError(
                f"Navigation discovery account-days are below selected accounts for {destination}."
            )
        expected_rate = (
            None
            if active_accounts == 0
            else round(100.0 * selected_accounts / active_accounts, 2)
        )
        if expected_rate is None:
            if rate is not None:
                raise ValueError(
                    f"Navigation discovery rate must be unavailable without active accounts for {destination}."
                )
        elif (
            not isinstance(rate, (int, float))
            or isinstance(rate, bool)
            or abs(float(rate) - expected_rate) > 0.005
        ):
            raise ValueError(
                f"Navigation discovery rate does not match its denominator for {destination}."
            )
        selected_by_destination[destination] = selected_accounts
        selected_days_by_destination[destination] = selected_account_days

    return {
        "status": "observed" if active_accounts else "awaiting_traffic",
        "measurement_since": rows[0]["measurement_since"],
        "window_since": rows[0]["window_since"],
        "window_until": rows[0]["window_until"],
        "active_workspace_accounts": active_accounts,
        "selected_accounts_by_destination": selected_by_destination,
        "selected_account_days_by_destination": selected_days_by_destination,
        "proves_destination_selection_only": True,
        "does_not_prove_task_completion": True,
    }


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

    validate_growth_funnel(sections["product_growth_funnel_snapshot"])
    validate_artifact_journey(sections["product_artifact_journey_snapshot"])
    navigation_discovery = validated_navigation_discovery(
        sections["product_navigation_discovery_snapshot"]
    )

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
    validate_growth_attribution_consistency(
        sections["product_growth_funnel_snapshot"],
        weekly_rows,
    )
    validate_project_continuity(
        sections["product_project_continuity_snapshot"],
        period_since=weekly["window"]["since"],
        period_until=weekly["window"]["until"],
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
        "navigation_discovery": navigation_discovery,
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
