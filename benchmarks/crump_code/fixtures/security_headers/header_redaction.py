"""Header logging boundary for the benchmark fixture."""


SENSITIVE_HEADERS = {"authorization", "x-api-key", "cookie"}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy safe for diagnostic logging."""
    return {
        name: "[REDACTED]" if name in SENSITIVE_HEADERS else value
        for name, value in headers.items()
    }
