"""Host-owned value oracle plans; NEVER import or execute candidate code here.

Use ``python -m scripts.crump_code_v2_observations`` for compatibility inventory.
Only three frozen contracts currently have a complete value-call translation.
All expectations remain in this host process, outside the serialized job.

A FUTURE trusted isolated adapter must invoke the admitted artifact, capture its
actual return/exception (including Python container family), enforce resource and
network limits, bind replies to this job, and separate stdout/logs from replies.
Guest-authored logs, pass counts, type claims or a copied request binding are NOT
execution evidence. This module supplies no such adapter or attestation. Even a
matching synthetic response is reported as UNVERIFIED, never as a model pass.
No hidden assertion code is placed in the candidate interpreter.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
import secrets
from typing import Any

from scripts.evaluate_crump_code_v2 import Candidate, load_suite, prepare_candidate


MAX_RESPONSE_BYTES = 32_768
MAX_JSON_NODES = 4_096
MAX_JSON_DEPTH = 12
MAX_STRING = 4_096
MAX_PENDING = 20
NONCE = re.compile(r"[0-9a-f]{64}\Z")


class ObservationError(ValueError):
    """A bounded, source-free protocol error."""


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _bounded_json(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    count = count if count is not None else [0]
    count[0] += 1
    if count[0] > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
        raise ObservationError("response_bound")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > 2**53 - 1:
            raise ObservationError("response_number")
        return
    if type(value) is float:
        if not math.isfinite(value) or abs(value) > 2**53 - 1:
            raise ObservationError("response_number")
        return
    if type(value) is str:
        if len(value) > MAX_STRING:
            raise ObservationError("response_bound")
        return
    if type(value) is list:
        for child in value:
            _bounded_json(child, depth + 1, count)
        return
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise ObservationError("response_shape")
            _bounded_json(key, depth + 1, count)
            _bounded_json(child, depth + 1, count)
        return
    raise ObservationError("response_shape")


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ObservationError("duplicate_json_key")
        result[key] = value
    return result


def _parse(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise ObservationError("response_bound")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ObservationError("response_number")))
        _bounded_json(value)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, ObservationError):
            raise
        raise ObservationError("response_invalid_json") from None
    if type(value) is not dict:
        raise ObservationError("response_shape")
    return value


@dataclass(frozen=True, slots=True)
class _Probe:
    module: str
    function: str
    args_json: bytes
    expected_outcome: str
    expected_type: str
    expected_json: bytes


def _returns(module: str, function: str, args: list[Any], kind: str, value: Any) -> _Probe:
    return _Probe(module, function, _json(args), "return", kind, _json(value))


def _raises(module: str, function: str, args: list[Any]) -> _Probe:
    return _Probe(module, function, _json(args), "raise", "ValueError", b"null")


def _probes(case_id: str) -> tuple[_Probe, ...]:
    # Original frozen hidden vectors translated into calls, not executed/imported.
    # Return types matter: tuple and list must not collapse at the JSON boundary.
    if case_id == "rename-boundary":
        good = _returns("inventory", "paths", [" M name with spaces.py\0R  new.py\0old.py\0"],
                        "list", ["name with spaces.py", "new.py", "old.py"])
        empty = _returns("inventory", "paths", [""], "list", [])
        bad = ["R  safe.py\0.env\0", " M .git/config\0", " M /tmp/a.py\0", "?? ../a.py\0",
               "?? a\\b.py\0", " M a.py", "R  a.py\0", "bad\0", "?? a.py \0"]
        return (good, empty, *(_raises("inventory", "paths", [raw]) for raw in bad))
    if case_id == "workspace-paths":
        good = ["src/a.py", "docs/a b.md", "a..b.txt"]
        bad = ["/a.py", "a//b.py", "a/./b.py", "a/../b.py", "C:/a.py", "a\\b.py", ".GIT/x.py",
               "x/.env/a.py", " a.py", "a.py ", "a\n.py", None, "img.png"]
        return (*(_returns("paths", "normalize", [path], "str", path) for path in good),
                *(_raises("paths", "normalize", [path]) for path in bad))
    if case_id == "image-size":
        good = [([4000, 4000, 4096, 4_000_000, 10, 100], [2000, 2000]),
                ([1000, 3000, 2000, 4_000_000, 10, 100], [666, 2000]),
                ([40, 20, 2000, 4_000_000, 10, 100], [40, 20])]
        bad = [[10, 10, 20, 400, 100, 100], [True, 10, 20, 400, 0, 100],
               [0, 10, 20, 400, 0, 100], [10, 10, 20, 400, -1, 100]]
        return (*(_returns("sizing", "prepare", args, "tuple", value) for args, value in good),
                *(_raises("sizing", "prepare", args) for args in bad))
    raise ObservationError("contract_requires_transport_extension")


# These are compatibility requirements, not claims that an adapter exists.
_COMPATIBILITY = {
    "activity-latest": ("object-identity", "merge input/result aliasing and nested detachment require object handles and independently captured mutations"),
    "gateway-retry": ("host-callback", "host-owned async send outcomes, call counts, exhaustion exceptions and actual yielding need callback RPC and scheduling evidence"),
    "sync-write-replay": ("stateful-callback", "store instances, replay after commit and DB callback keyword/count observations require persistent handles and host-owned callback RPC"),
    "quote-scope": ("identity-callback", "canonical hashing is a value subcase; exact receipt object identity and zero-charge callback proofs are not plain JSON values"),
    "provider-retry": ("host-callback", "run callback exception injection and independently counted executions require callback RPC"),
    "complete-patch": ("binary-callback", "read_bytes callbacks, bytes versus text, missing-file exceptions and exact callback behavior need typed binary/callback RPC"),
    "rename-boundary": ("value-calls", "fully translated; typed list returns and ValueError channel required"),
    "ignored-write": ("host-callback", "independent Git check/mkdir/write ordering and zero side effects require evaluator-owned callback endpoints; guest logs are not evidence"),
    "expiry-projection": ("host-callback", "selected projection and exact conditional DB update arguments require host-owned DB callback RPC"),
    "verification-repair": ("stateful-objects", "Workspace instance revisions, remembered checks and verdict calls require persistent object handles"),
    "cancel-begin": ("concurrency", "simultaneous begin/cancel tasks, atomicity and refund-once proof require trusted scheduling/object observations; sequential JSON calls are insufficient"),
    "daily-retention": ("stateful-objects", "Ledger reserve/erase/settle/release sequences and tuple totals require persistent object handles"),
    "workspace-paths": ("value-calls", "fully translated; exact string returns and ValueError channel required"),
    "signed-admission": ("binary-callback", "HMAC fixture uses bytes, policy bindings and zero-provision callbacks; requires typed binary/callback RPC; this is not RS256/OIDC"),
    "request-cost": ("non-json-value", "most subcases are value calls, but exact tuple returns and NaN rejection require a typed nonfinite-input constructor; not silently omitted"),
    "call-lease": ("concurrency", "30 concurrent begin calls, row immutability and takeover require trusted scheduling plus persistent object handles"),
    "image-size": ("value-calls", "fully translated; tuple result family, numeric values and ValueError channel required"),
    "image-recovery": ("object-identity", "whitelist values are JSON-compatible, but detached nested recovery aliasing needs independent object/mutation observations"),
    "startup-order": ("host-callback", "constructor/event callbacks and exactly-once order require evaluator-owned callback endpoints and persistent Boot instances"),
    "verification-feedback": ("stateful-callback", "actual verify/propose feedback, live workspace revision mutation and shared bound require host-owned callbacks and persistent handles"),
}


def compatibility_report() -> dict[str, Any]:
    suite = load_suite()
    if set(_COMPATIBILITY) != {case.id for case in suite.cases}:
        raise ObservationError("compatibility_inventory_drift")
    cases = [{"case_id": case.id, "stratum": case.stratum,
              "translation": "supported" if _COMPATIBILITY[case.id][0] == "value-calls" else "blocked",
              "requirement": _COMPATIBILITY[case.id][0], "detail": _COMPATIBILITY[case.id][1],
              "oracle_test_ids": list(case.oracle_test_ids), "fixture_sha256": case.fixture_sha256}
             for case in suite.cases]
    return {"schema_version": 1, "suite_id": suite.suite_id, "manifest_sha256": suite.manifest_sha256,
            "cases": cases, "supported_contracts": 3, "blocked_contracts": 17,
            "isolated_adapter_implemented": False, "capability_evaluated": False,
            "scope": "Complete value translation for three authored contracts; no model/VM quality result."}


@dataclass(frozen=True, slots=True)
class ObservationJob:
    """Only admitted source and call inputs; no expected results or oracle files."""
    candidate: Candidate
    request_json: bytes


@dataclass(frozen=True, slots=True)
class ObservationDecision:
    case_id: str | None
    status: str
    reason: str | None
    observations: int
    # Matching untrusted/synthetic JSON never authenticates an execution.
    execution_verified: bool = False
    capability_evaluated: bool = False


@dataclass(frozen=True, slots=True)
class _Plan:
    binding_json: bytes
    probes: tuple[_Probe, ...]


class ObservationSession:
    """One-shot host reducer. It authenticates NO VM and computes NO quality rate.

    A matching reply is merely ``observations_matched_unverified``. A trusted
    future transport must independently attest artifact execution before a caller
    can use these comparisons as evidence. Never expose this object to a guest.
    """

    def __init__(self) -> None:
        self._pending: dict[str, _Plan] = {}
        self._used: set[str] = set()

    def start(self, case_id: str, patch: str) -> ObservationJob:
        if len(self._pending) + len(self._used) >= MAX_PENDING:
            raise ObservationError("session_bound")
        suite = load_suite()
        case = suite.case(case_id)
        probes = _probes(case_id)  # Reject unsupported contracts before admission/remote execution.
        candidate = prepare_candidate(case, patch)
        nonce = secrets.token_hex(32)
        if nonce in self._pending or nonce in self._used:
            raise ObservationError("nonce_collision")
        binding = {"schema_version": 1, "suite_id": suite.suite_id, "manifest_sha256": suite.manifest_sha256,
                   "case_id": case.id, "fixture_sha256": candidate.fixture_sha256,
                   "candidate_sha256": candidate.candidate_sha256, "nonce": nonce}
        calls = [{"id": f"call-{index:03d}", "module": probe.module, "function": probe.function,
                  "args": json.loads(probe.args_json)} for index, probe in enumerate(probes)]
        self._pending[nonce] = _Plan(_json(binding), probes)
        return ObservationJob(candidate, _json({**binding, "calls": calls}))

    def consume(self, raw: bytes) -> ObservationDecision:
        """Compare bounded value observations; consume a known nonce even on rejection.

        Response keys are exactly request binding plus ``results``. Each result
        has id/outcome and either python_type/value or error_type. The trusted
        adapter must normalize builtin return/exception families (subclasses
        included). Primitive numeric equality follows the frozen unittest oracle,
        so 2000.0 equals 2000; container families still distinguish tuple/list.
        No logs,
        summaries, skip counts, pass flags or guest assertions are accepted.
        """
        case_id: str | None = None
        try:
            value = _parse(raw)
            nonce = value.get("nonce")
            if type(nonce) is not str or not NONCE.fullmatch(nonce):
                raise ObservationError("response_binding")
            if nonce in self._used:
                raise ObservationError("response_replayed")
            plan = self._pending.pop(nonce, None)
            if plan is None:
                raise ObservationError("response_unknown_nonce")
            self._used.add(nonce)
            binding = json.loads(plan.binding_json)
            case_id = binding["case_id"]
            if set(value) != {*binding, "results"} or _json({key: value[key] for key in binding}) != plan.binding_json:
                raise ObservationError("response_binding")
            results = value["results"]
            if type(results) is not list or len(results) != len(plan.probes):
                raise ObservationError("response_collection")
            by_id: dict[str, dict[str, Any]] = {}
            for result in results:
                if type(result) is not dict or type(result.get("id")) is not str or result["id"] in by_id:
                    raise ObservationError("response_collection")
                by_id[result["id"]] = result
            expected_ids = {f"call-{index:03d}" for index in range(len(plan.probes))}
            if set(by_id) != expected_ids:
                raise ObservationError("response_collection")
            for index, probe in enumerate(plan.probes):
                result = by_id[f"call-{index:03d}"]
                if probe.expected_outcome == "raise":
                    if set(result) != {"id", "outcome", "error_type"} or result["outcome"] != "raise" or result["error_type"] != probe.expected_type:
                        raise ObservationError("value_contract_rejected")
                elif (set(result) != {"id", "outcome", "python_type", "value"}
                      or result["outcome"] != "return" or result["python_type"] != probe.expected_type
                      or result["value"] != json.loads(probe.expected_json)):
                    raise ObservationError("value_contract_rejected")
            return ObservationDecision(case_id, "observations_matched_unverified", None, len(results))
        except (ObservationError, KeyError, TypeError, ValueError, OverflowError, RecursionError):
            return ObservationDecision(case_id, "observations_rejected", "untrusted_or_nonmatching_observations", 0)


def main() -> None:
    print(json.dumps(compatibility_report(), indent=2))


if __name__ == "__main__":
    main()
