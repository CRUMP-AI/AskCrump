from benchmarks.crump_code.fixtures.security_headers.header_redaction import redact_headers


def test_sensitive_header_names_are_case_insensitive():
    original = {
        "Authorization": "Bearer private",
        "X-API-Key": "private-key",
        "COOKIE": "session=private",
        "Content-Type": "application/json",
    }
    assert redact_headers(original) == {
        "Authorization": "[REDACTED]",
        "X-API-Key": "[REDACTED]",
        "COOKIE": "[REDACTED]",
        "Content-Type": "application/json",
    }


def test_input_is_not_mutated():
    original = {"Authorization": "Bearer private"}
    redact_headers(original)
    assert original == {"Authorization": "Bearer private"}
