"""Fail closed when a browser control points at a missing Ask Crump API route."""

from __future__ import annotations

from pathlib import Path
import re

from backend.application import create_app


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
PUBLIC_SUFFIXES = frozenset({".html", ".js"})
API_STRING = re.compile(r"(?P<quote>['\"`])(?P<value>/api/.*?)(?P=quote)")
TEMPLATE_EXPRESSION = re.compile(r"\$\{[^{}]*\}")
EXPECTED_RAW_REFERENCES = 97
EXPECTED_SOURCE_FILES = 27

# The final manuscript-run segment is deliberately selected from a fixed UI action.
# Keeping the exact source expression and its three server destinations here makes
# any widening of that action vocabulary an explicit review event.
DYNAMIC_ROUTE_FAMILIES = {
    "/api/manuscript-runs/${runId}/${action}": frozenset({
        "/api/manuscript-runs/{run_id}/cancel",
        "/api/manuscript-runs/{run_id}/pause",
        "/api/manuscript-runs/{run_id}/resume",
    }),
}


def browser_api_strings() -> dict[str, set[str]]:
    references: dict[str, set[str]] = {}
    for path in sorted(PUBLIC.rglob("*")):
        if not path.is_file() or path.suffix not in PUBLIC_SUFFIXES:
            continue
        relative = path.relative_to(ROOT).as_posix()
        for match in API_STRING.finditer(path.read_text(encoding="utf-8")):
            references.setdefault(match.group("value"), set()).add(relative)
    return references


def normalized_client_path(raw: str) -> str:
    def replace_expression(match: re.Match[str]) -> str:
        expression = match.group(0)
        # A template expression that produces an optional query string does not
        # change the route path.
        if "?" in expression:
            return ""
        return "{client_param}"

    path = TEMPLATE_EXPRESSION.sub(replace_expression, raw)
    path = path.split("?", 1)[0]
    return path.rstrip("/") or "/"


def segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def route_matches(client_path: str, server_path: str) -> bool:
    client_segments = segments(client_path)
    server_segments = segments(server_path)
    if len(client_segments) != len(server_segments):
        return False
    for client, server in zip(client_segments, server_segments, strict=True):
        client_parameter = client.startswith("{") and client.endswith("}")
        server_parameter = server.startswith("{") and server.endswith("}")
        if client_parameter:
            if not server_parameter:
                return False
        elif client != server:
            return False
    return True


def test_every_browser_api_destination_has_a_backend_route():
    application = create_app()
    server_routes = {
        route.path
        for route in application.routes
        if route.path.startswith("/api/")
    }
    references = browser_api_strings()
    assert references, "No browser API destinations were discovered."
    assert len(references) == EXPECTED_RAW_REFERENCES, (
        "Browser API reference inventory changed; review every added or removed destination."
    )
    assert len({source for sources in references.values() for source in sources}) == EXPECTED_SOURCE_FILES, (
        "Browser API source-file inventory changed; review the complete affected surface."
    )

    missing: list[str] = []
    for raw, sources in sorted(references.items()):
        if raw == "/api/":
            # Namespace classification in the service worker, not a request.
            continue
        if raw in DYNAMIC_ROUTE_FAMILIES:
            expected = DYNAMIC_ROUTE_FAMILIES[raw]
            if not expected.issubset(server_routes):
                missing.append(
                    f"{raw} ({', '.join(sorted(sources))}) -> "
                    f"missing {', '.join(sorted(expected - server_routes))}"
                )
            continue

        client_path = normalized_client_path(raw)
        if raw.endswith("/"):
            # A deliberately concatenated identifier must resolve to a one-segment
            # parameter route; a broad prefix match would hide dead destinations.
            prefix_segments = segments(client_path)
            matched = any(
                len(segments(route)) == len(prefix_segments) + 1
                and segments(route)[: len(prefix_segments)] == prefix_segments
                and segments(route)[-1].startswith("{")
                for route in server_routes
            )
        else:
            matched = any(route_matches(client_path, route) for route in server_routes)
        if not matched:
            missing.append(f"{raw} ({', '.join(sorted(sources))}) -> {client_path}")

    assert not missing, "Browser API destinations without backend routes:\n" + "\n".join(missing)


def test_dynamic_browser_api_families_are_exact_and_not_dead():
    references = browser_api_strings()
    observed = {raw for raw in references if "${action}" in raw}
    assert observed == set(DYNAMIC_ROUTE_FAMILIES)
