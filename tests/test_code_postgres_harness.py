"""Guard the disposable-only concurrency harness without needing a local DB."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/verify_code_budget_postgres.py"
SPEC = importlib.util.spec_from_file_location("code_postgres_fixture", PATH)
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


@pytest.mark.parametrize("host", ["db.production.example", "/var/run/postgresql", "", "localhost,remote", "127.0.0.1 remote"])
def test_fixture_rejects_non_loopback_destinations(host):
    with pytest.raises(ValueError, match="loopback"):
        HARNESS.fixture_environment({"PGHOST": host, "PGDATABASE": "askcrump_code_test_ci"})


@pytest.mark.parametrize("database", ["postgres", "askcrump", "askcrump_code_test_", "askcrump_code_test_foo;drop", "askcrump_code_test_" + "a" * 44])
def test_fixture_rejects_shared_or_unbounded_database_names(database):
    with pytest.raises(ValueError, match="isolated"):
        HARNESS.fixture_environment({"PGHOST": "localhost", "PGDATABASE": database})


@pytest.mark.parametrize("port", ["0", "65536", "5432 remote", "-1", "１２３"])
def test_fixture_rejects_invalid_port(port):
    with pytest.raises(ValueError, match="port"):
        HARNESS.fixture_environment({"PGHOST": "localhost", "PGDATABASE": "askcrump_code_test_ci", "PGPORT": port})


def test_fixture_strips_libpq_routing_and_service_overrides():
    env = HARNESS.fixture_environment(dict(PGHOST="127.0.0.1", PGDATABASE="askcrump_code_test_ci",
        PGUSER="postgres", PGPASSWORD="fixture-only", PGSERVICE="production", PGHOSTADDR="remote",
        PGSERVICEFILE="/prod", PGPASSFILE="/prod-secrets", PGOPTIONS="-c unsafe=1", PATH="bin"))
    assert not {"PGSERVICE", "PGHOSTADDR", "PGSERVICEFILE", "PGPASSFILE"} & env.keys()
    assert env["PGOPTIONS"] == "-c statement_timeout=12000 -c lock_timeout=10000"
    assert env["PATH"] == "bin"


def test_literal_preserves_quotes_without_executing_sql():
    assert HARNESS.literal("x';drop table users;--") == "'x'';drop table users;--'"
    with pytest.raises(ValueError):
        HARNESS.invocation("unsafe;select", "fixture")
