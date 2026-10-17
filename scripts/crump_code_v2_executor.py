"""Evaluator-owned executor boundary — offline fake-interface hardening.

PLUMBING EVIDENCE ONLY. This module defines the narrow contract between the
thing that runs an agent candidate and the thing that decides whether it
passed. The executor owns evaluation; the agent never touches the oracle,
the reference solution, or the verdict.

HONESTY FRAMING (read before relying on any of this):
- Hash consistency is NOT authenticity. Matching digests prove the bytes
  are the bytes that were bound — nothing about where they came from.
- Revoking mock tools and scanning candidate bytes for reference content do
  NOT prove live isolation. They are mechanical checks inside a fake; the
  production isolation boundary is separately owned and still open.
- Candidate code remains UNTRUSTED for whenever it is eventually executed.
  Nothing here executes candidate code and nothing here vouches for it.
- Fake receipts prove the interface refuses correctly (plumbing). They prove
  nothing about model capability. Per-case labels stay
  "Not evaluated (model evaluation not run)"; fix_rate stays null.

REPLAY SCOPE (explicit): one-use-handle replay protection covers THIS
executor instance's in-memory private registry only. It does not survive
process restart, is not shared across executor instances, and is not a
distributed guarantee. Cross-instance replay protection is out of scope.

No credentials, no paid services, no live candidate execution, no model
calls, no production security changes.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, NoReturn

# ---------------------------------------------------------------------------
# Strict input discipline (same as scripts/crump_code_v2_status.py):
# actual types only — truthy strings like "false" are refused, never coerced.
# ---------------------------------------------------------------------------

_TERMINAL_TEST_STATUSES = frozenset({"pass", "fail"})
_NON_TERMINAL_TEST_STATUSES = frozenset({"error", "skipped"})
_KNOWN_TEST_STATUSES = _TERMINAL_TEST_STATUSES | _NON_TERMINAL_TEST_STATUSES

_OUTCOMES = frozenset({"pass", "fail", "incomplete", "timeout", "cancelled"})

# Pre-execution refusal codes (BoundaryRefusal). Mechanical, neutral.
CODE_BINDING_MISMATCH = "binding_mismatch"
CODE_UNKNOWN_HANDLE = "unknown_handle"
CODE_REPLAYED_HANDLE = "replayed_handle"
CODE_RUN_TERMINATED = "run_terminated"

# Accepted-run incomplete reason codes. Mechanical, neutral — never claims of
# forgery or tampering.
REASON_MISSING_TEST_ID = "missing_test_id"
REASON_DUPLICATE_TEST_ID = "duplicate_test_id"
REASON_EXTRA_TEST_ID = "extra_test_id"
REASON_NON_TERMINAL_TEST_RECORD = "non_terminal_test_record"
REASON_EVIDENCE_DIGEST_MISMATCH = "evidence_digest_mismatch"
REASON_AGENT_SURFACE_VIOLATION = "agent_surface_violation"
REASON_REFERENCE_BYTES_PRESENT = "reference_bytes_present"
REASON_DEADLINE_EXPIRED = "deadline_expired"
REASON_CANCEL_ACCEPTED = "cancel_accepted"
REASON_MALFORMED_EVIDENCE = "malformed_evidence"
REASON_EVIDENCE_RECORDS_MISMATCH = "evidence_records_mismatch"


class BoundaryRefusal(Exception):
    """A pre-execution refusal. Distinct from an accepted-run outcome.

    Raised (never returned as an outcome) when the boundary itself rejects
    the request: bad binding, unknown/fabricated handle, replayed handle, or
    an operation against a terminated run.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _refuse(code: str, detail: str) -> NoReturn:
    raise BoundaryRefusal(code, detail)


_MISSING = object()


def _descriptor_field(obj: object, name: str) -> Any:
    """Read a run-descriptor field defensively.

    The caller may pass any attribute-bearing object; a missing attribute
    is a binding refusal, never an AttributeError escaping to the caller.
    """
    value = getattr(obj, name, _MISSING)
    if value is _MISSING:
        _refuse(CODE_BINDING_MISMATCH, f"run descriptor is missing field {name!r}")
    return value


def _require_str(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        _refuse(
            CODE_BINDING_MISMATCH,
            f"{where} must be a non-empty string, got {type(value).__name__} ({value!r})",
        )
    return value


def _require_bytes(value: object, where: str) -> bytes:
    # Snapshot: callers may hand us a mutable bytearray; we copy so later
    # mutation cannot change what was bound.
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    _refuse(
        CODE_BINDING_MISMATCH,
        f"{where} must be bytes-like, got {type(value).__name__}",
    )


def _require_mapping(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _refuse(
            CODE_BINDING_MISMATCH,
            f"{where} must be a mapping, got {type(value).__name__}",
        )
    return value


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze a provenance declaration.

    The result is immutable AND marked untrusted: the executor records it
    for audit purposes only and never branches on it.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Anything else is not a declarable provenance value.
    _refuse(
        CODE_BINDING_MISMATCH,
        f"provenance contains a non-declarable value of type {type(value).__name__}",
    )


# ---------------------------------------------------------------------------
# Clock (injectable for race tests)
# ---------------------------------------------------------------------------


class SystemClock:
    """Production-shaped clock: monotonic for deadlines, UTC for records."""

    def monotonic(self) -> float:
        import time

        return time.monotonic()

    def utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class FakeClock:
    """Injectable clock for deterministic race tests."""

    def __init__(self, start_monotonic: float = 1000.0) -> None:
        self._mono = float(start_monotonic)
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            return self._mono

    def utcnow(self) -> str:
        # Informational only; derived from the fake monotonic reading so two
        # runs with the same scripted clock are comparable.
        with self._lock:
            base = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
            return datetime.fromtimestamp(
                base + (self._mono - 1000.0), tz=timezone.utc
            ).isoformat()

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._mono += float(seconds)


# ---------------------------------------------------------------------------
# Frozen run / evidence / result records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrozenRun:
    """The caller's declaration of what is to be evaluated.

    Every digest is VERIFIED by the executor against its own frozen state at
    bind time; a declaration alone binds nothing. `provenance` is deep-frozen
    and treated as an UNTRUSTED declaration: recorded, never trusted, never
    branched on.
    """

    run_id: str
    case_id: str
    corpus_manifest_sha: str
    candidate_artifact_sha: str
    oracle_suite_sha: str
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TestRecord:
    __test__ = False  # not a pytest test class; it is a result record type.

    test_id: str
    status: str  # "pass" | "fail" | "error" | "skipped"


@dataclass(frozen=True)
class EvidenceBundle:
    """Evidence submitted for one evaluation.

    The executor recomputes sha256(evidence_bytes) and compares it to the
    declared evidence_sha256; a mismatch can never establish any outcome
    other than incomplete.
    """

    test_records: tuple[TestRecord, ...]
    evidence_bytes: bytes
    evidence_sha256: str


def canonical_evidence_bytes(records: tuple[TestRecord, ...]) -> bytes:
    """Canonical serialization of authoritative test records.

    The executor derives its verdict from the DIGESTED BYTES, never from
    caller-supplied record objects alone — so this canonical form is the
    single source of truth for what "the evidence says". The digest and
    the graded records are always the same data.
    """
    pairs = [[r.test_id, r.status] for r in records]
    return json.dumps(pairs, sort_keys=True, separators=(",", ":")).encode("utf-8")


class _MalformedEvidence(Exception):
    """Producer output that fails type/schema validation.

    Converted by the caller into an immutable `incomplete` result with a
    mechanical reason code and retained safe diagnostics — never a crash,
    never a stranded handle.
    """

    def __init__(self, reason: str, diagnostics: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class _ValidatedEvidence:
    """Evidence after strict validation. The snapshot is taken ONCE; every
    later step (digest check, parsing, grading, receipt) uses the snapshot,
    never the caller-supplied bytes object again. The digest is computed
    once here and cached — receipt creation never rehashes."""

    snapshot: bytes
    records: tuple[TestRecord, ...]  # derived FROM the snapshot bytes
    declared_sha256: str
    digest: str  # sha256(snapshot), computed once at validation time


@dataclass(frozen=True)
class OracleResult:
    """The executor's verdict. Constructed ONLY from executor state.

    `execution_kind` is executor-assigned and always "fake"; the caller
    cannot upgrade it. `expected_test_ids` are the frozen suite's exact
    unique IDs for the case; `test_records` are what the evidence carried.
    """

    run_id: str
    case_id: str
    executor_id: str
    sequence: int
    execution_kind: str
    outcome: str  # one of _OUTCOMES
    reason_code: str | None
    expected_test_ids: tuple[str, ...]
    test_records: tuple[TestRecord, ...]
    evidence_sha256: str | None
    evaluated_at: str  # informational UTC timestamp, executor clock
    # Bound-artifact digests, from executor state at bind time, so an
    # exported receipt identifies the actual artifacts that were bound.
    corpus_manifest_sha: str
    candidate_artifact_sha: str
    oracle_suite_sha: str
    # The immutable retained evidence snapshot (defect 4): the exact bytes
    # the verdict was derived from, so the audit digest can be recomputed
    # and checked later. Never the caller's object — always the snapshot.
    evidence_snapshot: bytes | None = None
    # Safe diagnostics only (type names, short reasons) — never raw
    # evidence bytes or secrets.
    diagnostics: str | None = None


# ---------------------------------------------------------------------------
# Revoked agent surface (mock)
# ---------------------------------------------------------------------------


class RevokedAgentSurface:
    """The agent tool surface as seen during oracle evaluation: revoked.

    Any invocation attempt is refused and recorded. HONESTY NOTE: revoking
    mock tools does NOT prove live isolation — it exercises the refusal
    mechanism inside the fake. Production isolation is separately owned.
    """

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def invoke(self, name: str, **kwargs: Any) -> NoReturn:
        self.attempts.append(str(name))
        raise BoundaryRefusal(
            REASON_AGENT_SURFACE_VIOLATION,
            f"agent surface is revoked during oracle evaluation (attempted: {name})",
        )


# ---------------------------------------------------------------------------
# The executor
# ---------------------------------------------------------------------------


class _BoundRun:
    """Executor-owned mutable run state. Never exposed to callers."""

    __slots__ = (
        "handle",
        "frozen",
        "candidate_bytes",
        "provenance_frozen",
        "state",
        "consumed",
        "deadline_monotonic",
        "sequence",
        "result",
    )

    def __init__(
        self,
        *,
        handle: str,
        frozen: FrozenRun,
        candidate_bytes: bytes,
        deadline_monotonic: float,
        sequence: int,
    ) -> None:
        self.handle = handle
        self.frozen = frozen
        self.candidate_bytes = candidate_bytes
        self.provenance_frozen = _deep_freeze(dict(frozen.provenance))
        self.state = "issued"
        self.consumed = False
        self.deadline_monotonic = deadline_monotonic
        self.sequence = sequence
        # The single immutable terminal result, shared by every read path.
        self.result: OracleResult | None = None


class FakeBoundaryExecutor:
    """Evaluator-owned fake executor implementing the boundary contract.

    The executor loads the frozen corpus itself (manifest + oracle files)
    and verifies every digest the caller declares. Handles live in a
    private in-memory registry; each handle is atomically consumed before
    execution, so concurrent or repeated use cannot double-execute.
    """

    def __init__(
        self,
        corpus_root: str | Path,
        *,
        clock: Any | None = None,
        executor_id: str = "fake-boundary-executor",
        default_deadline_seconds: float = 300.0,
        _hooks: dict[str, Any] | None = None,
    ) -> None:
        self.corpus_root = Path(corpus_root)
        self._clock = clock or SystemClock()
        # Test-only seams (defect 3): named hooks invoked at fixed points so
        # tests can interleave deterministically (mutate between snapshot and
        # finalization, advance the fake clock mid-phase). Never used in
        # production paths; a raising hook is a test bug and propagates.
        self._hooks: dict[str, Any] = dict(_hooks) if _hooks else {}
        self.executor_id = str(executor_id)
        self._default_deadline = float(default_deadline_seconds)
        self._lock = threading.Lock()
        self._registry: dict[str, _BoundRun] = {}
        self._sequence = 0
        # Frozen evaluator-side state, computed once from the corpus.
        manifest_path = self.corpus_root / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        self._manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        self._expected_ids: dict[str, tuple[str, ...]] = {}
        for case in manifest["cases"]:
            ids = case["oracle_test_ids"]
            if (
                not isinstance(ids, list)
                or not ids
                or any(not isinstance(i, str) or not i for i in ids)
                or len(set(ids)) != len(ids)
            ):
                raise ValueError(
                    f"frozen corpus case {case.get('id')} has invalid oracle_test_ids"
                )
            self._expected_ids[str(case["id"])] = tuple(ids)
        self._oracle_suite_sha = self._compute_oracle_suite_sha()
        # Reference bytes per case for the exclusion scan. Evaluator-side
        # only: the agent side never receives these.
        self._reference_blobs: dict[str, list[bytes]] = {}
        cases_root = self.corpus_root / "cases"
        for case_id in self._expected_ids:
            blobs: list[bytes] = []
            ref_dir = cases_root / case_id / "reference"
            if ref_dir.is_dir():
                for path in sorted(ref_dir.rglob("*")):
                    if path.is_file():
                        blobs.append(path.read_bytes())
            self._reference_blobs[case_id] = blobs

    # -- frozen digests ----------------------------------------------------

    def _compute_oracle_suite_sha(self) -> str:
        entries: list[list[str]] = []
        cases_root = self.corpus_root / "cases"
        for case_dir in sorted(cases_root.iterdir()):
            if not case_dir.is_dir():
                continue
            oracle_dir = case_dir / "oracle"
            if not oracle_dir.is_dir():
                continue
            for path in sorted(oracle_dir.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(self.corpus_root).as_posix()
                    entries.append(
                        [
                            case_dir.name,
                            rel,
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                        ]
                    )
        canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def manifest_sha256(self) -> str:
        return self._manifest_sha

    @property
    def oracle_suite_sha256(self) -> str:
        return self._oracle_suite_sha

    def expected_test_ids(self, case_id: str) -> tuple[str, ...]:
        try:
            return self._expected_ids[case_id]
        except KeyError:
            _refuse(CODE_BINDING_MISMATCH, f"unknown case_id: {case_id!r}")

    @property
    def agent_surface(self) -> RevokedAgentSurface:
        """The agent tool surface: always revoked. See HONESTY FRAMING."""
        return RevokedAgentSurface()

    # -- bind --------------------------------------------------------------

    def bind(self, frozen: FrozenRun, candidate_bytes: Any) -> str:
        """Bind a declared run to snapshotted bytes. Returns a one-use handle.

        Refuses (BoundaryRefusal, code binding_mismatch) unless every
        declared digest matches the executor's frozen state and every field
        is the right actual type.
        """
        # Descriptor fields are read defensively: a caller may hand us any
        # object with attributes (e.g. a mutable SimpleNamespace). Missing
        # attributes are a binding refusal, not an AttributeError.
        run_id = _require_str(_descriptor_field(frozen, "run_id"), "run_id")
        case_id = _require_str(_descriptor_field(frozen, "case_id"), "case_id")
        manifest_sha = _require_str(
            _descriptor_field(frozen, "corpus_manifest_sha"), "corpus_manifest_sha"
        )
        artifact_sha = _require_str(
            _descriptor_field(frozen, "candidate_artifact_sha"), "candidate_artifact_sha"
        )
        oracle_sha = _require_str(
            _descriptor_field(frozen, "oracle_suite_sha"), "oracle_suite_sha"
        )
        provenance = _require_mapping(
            _descriptor_field(frozen, "provenance"), "provenance"
        )
        snapshot = _require_bytes(candidate_bytes, "candidate_bytes")

        if manifest_sha != self._manifest_sha:
            _refuse(
                CODE_BINDING_MISMATCH,
                "corpus_manifest_sha does not match the frozen manifest",
            )
        if case_id not in self._expected_ids:
            _refuse(CODE_BINDING_MISMATCH, f"unknown case_id: {case_id!r}")
        if oracle_sha != self._oracle_suite_sha:
            _refuse(
                CODE_BINDING_MISMATCH,
                "oracle_suite_sha does not match the frozen oracle suite",
            )
        if hashlib.sha256(snapshot).hexdigest() != artifact_sha:
            _refuse(
                CODE_BINDING_MISMATCH,
                "candidate_artifact_sha does not match the presented bytes",
            )

        handle = f"hdl_{uuid.uuid4().hex}"
        with self._lock:
            if any(r.frozen.run_id == run_id for r in self._registry.values()):
                _refuse(CODE_BINDING_MISMATCH, f"run_id already bound: {run_id!r}")
            self._sequence += 1
            # Executor-owned descriptor: reconstructed from validated
            # snapshots only. The caller's object is NEVER retained, so a
            # later mutation of the caller's object cannot change the
            # expected suite, the receipt identity, or the replay checks.
            owned = FrozenRun(
                run_id=run_id,
                case_id=case_id,
                corpus_manifest_sha=manifest_sha,
                candidate_artifact_sha=artifact_sha,
                oracle_suite_sha=oracle_sha,
                provenance=_deep_freeze(dict(provenance)),
            )
            record = _BoundRun(
                handle=handle,
                frozen=owned,
                candidate_bytes=snapshot,
                deadline_monotonic=self._clock.monotonic() + self._default_deadline,
                sequence=self._sequence,
            )
            self._registry[handle] = record
        return handle

    # -- cancel ------------------------------------------------------------

    def cancel(self, handle: str) -> str:
        """Accept cancellation for an issued or running run.

        Every read path shares the single stored terminal result: if a
        result was already stored, its outcome is returned. Terminal states
        are immutable. An accepted cancellation consumes the handle, so no
        later evaluation can produce a pass for the run.

        Timeout/cancel precedence: an observed expired deadline wins unless
        the cancellation was already accepted before expiry. If the
        deadline is already expired when cancel is called, the run resolves
        to timeout immediately — the late cancellation does not overwrite it.
        """
        with self._lock:
            record = self._registry.get(handle)
            if record is None:
                _refuse(
                    CODE_UNKNOWN_HANDLE, "no such handle in this executor's registry"
                )
            if record.result is not None:
                return record.result.outcome
            now = self._clock.monotonic()
            if now >= record.deadline_monotonic:
                # Observed expired deadline: timeout wins. The cancellation
                # was not accepted before expiry, so no cancelled outcome is
                # produced. Store the single terminal receipt now so every
                # read path agrees.
                result = self._store_terminal(
                    record, "timeout", REASON_DEADLINE_EXPIRED, (), None
                )
            elif record.state in ("issued", "running"):
                # Cancellation accepted before expiry: it wins.
                result = self._store_terminal(
                    record, "cancelled", REASON_CANCEL_ACCEPTED, (), None
                )
            else:
                return record.state  # defensive; unreachable in practice
            record.consumed = True
            return result.outcome

    # -- evaluate ----------------------------------------------------------

    def evaluate(self, handle: str, evidence: EvidenceBundle) -> OracleResult:
        """Evaluate bound evidence. The handle is atomically consumed first.

        Raises BoundaryRefusal (unknown_handle / replayed_handle /
        run_terminated) for pre-execution problems. Returns an OracleResult
        with an explicit outcome otherwise — never raises for evidence
        problems; those become immutable incomplete outcomes with mechanical
        codes. Malformed producer output can never strand the handle: every
        path stores exactly one immutable terminal result, shared by all
        read paths.

        Timeout/cancel precedence: an accepted cancellation before expiry
        wins; otherwise an observed expired deadline wins.
        """
        with self._lock:
            record = self._registry.get(handle)
            if record is None:
                _refuse(
                    CODE_UNKNOWN_HANDLE, "no such handle in this executor's registry"
                )
            if record.consumed:
                _refuse(CODE_REPLAYED_HANDLE, "handle already consumed")
            if record.result is not None or record.state != "issued":
                _refuse(CODE_RUN_TERMINATED, f"run is already {record.state}")
            # Atomic consumption happens BEFORE any execution.
            record.consumed = True
            if self._clock.monotonic() >= record.deadline_monotonic:
                # Observed expired deadline and no prior terminal result:
                # timeout wins.
                return self._store_terminal(
                    record, "timeout", REASON_DEADLINE_EXPIRED, (), None
                )
            record.state = "running"

        # Everything below this point converts ordinary failures into the
        # SHARED incomplete receipt via _terminalize — never a crash, never
        # a stranded handle, never weakened identity. True pre-execution
        # handle/binding refusals above stay as BoundaryRefusal. BaseException
        # (KeyboardInterrupt/SystemExit) is never swallowed: only Exception
        # subclasses are converted.
        try:
            validated = self._validate_evidence(evidence)
        except _MalformedEvidence as exc:
            return self._terminalize(
                record, "incomplete", exc.reason, (), None, exc.diagnostics
            )
        except Exception as exc:  # noqa: BLE001 - snapshot/decoder safety net
            # e.g. ValueError from bytes() on a released memoryview,
            # RecursionError from pathological JSON. Never BaseException.
            return self._terminalize(
                record,
                "incomplete",
                REASON_MALFORMED_EVIDENCE,
                (),
                None,
                f"{type(exc).__name__} during evidence validation",
            )

        # Oracle phase. The agent surface is revoked for the whole phase;
        # HONESTY NOTE: this exercises the refusal mechanism in the fake and
        # does not prove live isolation.
        surface = RevokedAgentSurface()
        try:
            outcome, reason, records = self._oracle_phase(record, validated, surface)
        except BoundaryRefusal as exc:
            # A revoked-surface attempt escaping a callback: record the
            # attempt as an agent-surface violation, never a crash and never
            # a stranded handle.
            return self._terminalize(
                record,
                "incomplete",
                REASON_AGENT_SURFACE_VIOLATION,
                (),
                validated,
                f"agent surface attempt refused: {exc.code}",
            )
        except Exception as exc:  # noqa: BLE001 - callback safety net
            # A callback raising must not crash the report or strand the
            # handle: convert to an immutable incomplete with diagnostics.
            # Never BaseException: KeyboardInterrupt/SystemExit propagate.
            return self._terminalize(
                record,
                "incomplete",
                REASON_MALFORMED_EVIDENCE,
                (),
                validated,
                f"oracle phase raised {type(exc).__name__}",
            )

        # Expensive checks are done. Cheap final checks run WITHOUT the lock;
        # the unified terminal gate below re-checks the deadline immediately
        # before the atomic store, so no path can store `pass` after expiry.
        outcome, reason = self._apply_final_checks(record, outcome, reason)
        return self._terminalize(record, outcome, reason, records, validated)

    def _terminalize(
        self,
        record: _BoundRun,
        outcome: str,
        reason: str | None,
        records: tuple[TestRecord, ...],
        validated: _ValidatedEvidence | None,
        diagnostics: str | None = None,
    ) -> OracleResult:
        """The single unified terminal gate (defect 2).

        Every terminal path funnels through here: preserve any already-
        stored terminal receipt (a cancellation/timeout that won a race);
        otherwise an observed expired deadline wins; otherwise the computed
        outcome is stored atomically. The deadline check and the store run
        under the same lock with nothing between them, so final checks can
        never cross the deadline and still store `pass`.
        """
        with self._lock:
            if record.result is not None:
                return record.result
            if self._clock.monotonic() >= record.deadline_monotonic:
                # Observed expired deadline: timeout wins over whatever
                # outcome was computed (a cancellation accepted before
                # expiry would already have stored its receipt above).
                return self._store_terminal(
                    record, "timeout", REASON_DEADLINE_EXPIRED, (), validated
                )
            return self._store_terminal(
                record, outcome, reason, records, validated, diagnostics
            )

    def _validate_evidence(self, evidence: object) -> _ValidatedEvidence:
        """Strictly validate producer output; derive records from the bytes.

        The digest and the graded records are ALWAYS the same data: the
        verdict is derived from the snapshotted bytes, and the submitted
        record objects must exactly match what the bytes say. Any problem
        raises _MalformedEvidence (converted to immutable incomplete by the
        caller) — nothing here raises to the caller as a crash.
        """
        def bad(reason: str, detail: str) -> NoReturn:
            # Safe diagnostics: type names and short reasons only — never
            # raw evidence content.
            raise _MalformedEvidence(reason, f"malformed evidence: {detail}")

        if not isinstance(evidence, EvidenceBundle):
            bad(
                REASON_MALFORMED_EVIDENCE,
                f"expected EvidenceBundle, got {type(evidence).__name__}",
            )
        raw = evidence.evidence_bytes
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            bad(
                REASON_MALFORMED_EVIDENCE,
                f"evidence_bytes must be bytes-like, got {type(raw).__name__}",
            )
        # Snapshot ONCE. Everything downstream — digest check, parsing,
        # grading, receipt — uses this snapshot, never the caller's object.
        # A released memoryview (or other unreadable buffer) raises here;
        # that is malformed input, never a crash.
        try:
            snapshot = bytes(raw)
        except (ValueError, MemoryError) as exc:
            bad(
                REASON_MALFORMED_EVIDENCE,
                f"evidence bytes unreadable ({type(exc).__name__})",
            )
        # Test seam (defect 3): runs after the snapshot is taken, before any
        # use of it — lets tests mutate the ORIGINAL object to prove the
        # receipt reflects the snapshot, or advance the fake clock mid-phase.
        hook = self._hooks.get("after_snapshot")
        if hook is not None:
            hook(raw, snapshot)
        # The digest is computed ONCE here and cached on the validated
        # record — receipt creation never rehashes.
        digest = hashlib.sha256(snapshot).hexdigest()
        declared = evidence.evidence_sha256
        if not isinstance(declared, str) or not declared:
            bad(REASON_MALFORMED_EVIDENCE, "evidence_sha256 must be a non-empty string")
        if digest != declared:
            raise _MalformedEvidence(
                REASON_EVIDENCE_DIGEST_MISMATCH,
                "evidence digest does not match evidence bytes",
            )
        try:
            parsed = json.loads(snapshot.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            bad(
                REASON_MALFORMED_EVIDENCE,
                f"evidence bytes are not canonical JSON ({type(exc).__name__})",
            )
        if not isinstance(parsed, list):
            bad(REASON_MALFORMED_EVIDENCE, "evidence must be a JSON list of pairs")
        derived: list[TestRecord] = []
        for index, item in enumerate(parsed):
            if not isinstance(item, list) or len(item) != 2:
                bad(REASON_MALFORMED_EVIDENCE, f"record {index} is not a [test_id, status] pair")
            test_id, status = item
            if not isinstance(test_id, str) or not test_id:
                bad(REASON_MALFORMED_EVIDENCE, f"record {index} has an invalid test_id")
            if not isinstance(status, str) or status not in _KNOWN_TEST_STATUSES:
                bad(
                    REASON_MALFORMED_EVIDENCE,
                    f"record {index} has an unknown status",
                )
            derived.append(TestRecord(test_id=test_id, status=status))
        submitted = evidence.test_records
        if not isinstance(submitted, tuple) or not all(
            isinstance(r, TestRecord) for r in submitted
        ):
            bad(REASON_MALFORMED_EVIDENCE, "test_records must be a tuple of TestRecord")
        if [(r.test_id, r.status) for r in submitted] != [
            (r.test_id, r.status) for r in derived
        ]:
            raise _MalformedEvidence(
                REASON_EVIDENCE_RECORDS_MISMATCH,
                "submitted test_records do not match the evidence bytes",
            )
        return _ValidatedEvidence(
            snapshot=snapshot,
            records=tuple(derived),
            declared_sha256=declared,
            digest=digest,
        )

    def _oracle_phase(
        self,
        record: _BoundRun,
        validated: _ValidatedEvidence,
        surface: RevokedAgentSurface,
    ) -> tuple[str, str | None, tuple[TestRecord, ...]]:
        """Apply the pass rules mechanically to bytes-derived records.

        `validated.records` were derived from the snapshotted evidence
        bytes (whose digest was verified upstream) — the graded records
        and the digest are always the same data. `surface` is part of the
        test seam (revocation assertions live in tests).
        """
        records = validated.records
        expected = self._expected_ids[record.frozen.case_id]
        ids = [r.test_id for r in records]

        # Duplicate IDs can never establish anything.
        if len(set(ids)) != len(ids):
            return "incomplete", REASON_DUPLICATE_TEST_ID, records
        idset = set(ids)
        expected_set = set(expected)
        # Extra IDs are rejected as extra (mechanical, not a tampering claim).
        if idset - expected_set:
            return "incomplete", REASON_EXTRA_TEST_ID, records
        # Missing IDs: partial evidence. A partial set that contains a
        # failure is still incomplete — and the failure is RETAINED, not
        # dropped and not upgraded.
        if idset != expected_set:
            return "incomplete", REASON_MISSING_TEST_ID, records
        # Non-terminal records (error/skipped) cannot establish pass.
        if any(r.status in _NON_TERMINAL_TEST_STATUSES for r in records):
            return "incomplete", REASON_NON_TERMINAL_TEST_RECORD, records
        if any(r.status == "fail" for r in records):
            return "fail", None, records
        return "pass", None, records

    def _check_reference_exclusion(self, record: _BoundRun) -> str | None:
        """Byte-scan the bound candidate for reference-solution content.

        HONESTY NOTE: scanning bytes does not prove live isolation; it is a
        mechanical tripwire inside the fake. Returns a reason code or None.
        """
        for blob in self._reference_blobs.get(record.frozen.case_id, []):
            if blob and blob in record.candidate_bytes:
                return REASON_REFERENCE_BYTES_PRESENT
        return None

    def _apply_final_checks(
        self, record: _BoundRun, outcome: str, reason: str | None
    ) -> tuple[str, str | None]:
        """Compute every final check BEFORE the single atomic store.

        Reference exclusion is enforced on every terminal pass: a
        candidate smuggling reference bytes can never pass, even with
        all-pass records.
        """
        if outcome == "pass":
            exclusion = self._check_reference_exclusion(record)
            if exclusion is not None:
                return "incomplete", exclusion
        return outcome, reason

    def _store_terminal(
        self,
        record: _BoundRun,
        outcome: str,
        reason: str | None,
        records: tuple[TestRecord, ...],
        validated: _ValidatedEvidence | None,
        diagnostics: str | None = None,
    ) -> OracleResult:
        """Atomically store the ONE immutable terminal result.

        All final checks must be computed BEFORE this call. The result is
        built entirely from executor state (never caller objects): the
        bound digests come from the executor-owned descriptor, the evidence
        digest from the validated snapshot. Every read path (evaluate,
        cancel) shares this single stored result.
        """
        if record.result is not None:
            return record.result  # defensive: callers check first
        result = OracleResult(
            run_id=record.frozen.run_id,
            case_id=record.frozen.case_id,
            executor_id=self.executor_id,
            sequence=record.sequence,
            # Executor-assigned, always fake, never caller-upgradable.
            execution_kind="fake",
            outcome=outcome,
            reason_code=reason,
            expected_test_ids=self._expected_ids[record.frozen.case_id],
            test_records=records,
            # The digest was computed once at validation time and cached —
            # never rehashed here.
            evidence_sha256=(
                validated.digest if validated is not None else None
            ),
            # Informational UTC timestamp on the executor clock.
            evaluated_at=self._clock.utcnow(),
            corpus_manifest_sha=record.frozen.corpus_manifest_sha,
            candidate_artifact_sha=record.frozen.candidate_artifact_sha,
            oracle_suite_sha=record.frozen.oracle_suite_sha,
            # The immutable retained snapshot (defect 4): the exact bytes
            # the verdict was derived from, so the audit digest can be
            # recomputed and checked later.
            evidence_snapshot=(
                validated.snapshot if validated is not None else None
            ),
            diagnostics=diagnostics,
        )
        record.state = outcome
        record.result = result
        return result


# ---------------------------------------------------------------------------
# Malicious fake producer (test-only adversary)
# ---------------------------------------------------------------------------


class MaliciousFakeProducer:
    """A small adversarial producer for boundary tests. No model needed.

    Each method attempts one boundary violation against a
    FakeBoundaryExecutor. Every attempt must be refused with a mechanical
    reason code — the tests assert exactly that.
    """

    def __init__(self, executor: FakeBoundaryExecutor) -> None:
        self.executor = executor
        self.refusals: list[str] = []

    def _note(self, code: str) -> str:
        self.refusals.append(code)
        return code

    def replay_handle(self, handle: str, evidence: EvidenceBundle) -> str:
        """Evaluate twice on the same handle; the second must be refused."""
        self.executor.evaluate(handle, evidence)  # first use is legitimate
        try:
            self.executor.evaluate(handle, evidence)
        except BoundaryRefusal as exc:
            return self._note(exc.code)
        return self._note("NOT_REFUSED")

    def use_fabricated_handle(self, evidence: EvidenceBundle) -> str:
        try:
            self.executor.evaluate("hdl_fabricated_not_issued", evidence)
        except BoundaryRefusal as exc:
            return self._note(exc.code)
        return self._note("NOT_REFUSED")

    def use_foreign_handle(self, foreign_handle: str, evidence: EvidenceBundle) -> str:
        """A handle issued by another executor's private registry is unknown here."""
        try:
            self.executor.evaluate(foreign_handle, evidence)
        except BoundaryRefusal as exc:
            return self._note(exc.code)
        return self._note("NOT_REFUSED")

    def submit_forged_evidence(
        self, handle: str, evidence: EvidenceBundle, tampered: bytes
    ) -> OracleResult:
        """Evidence bytes that don't match the declared digest."""
        forged = EvidenceBundle(
            test_records=evidence.test_records,
            evidence_bytes=tampered,
            evidence_sha256=evidence.evidence_sha256,
        )
        return self.executor.evaluate(handle, forged)

    def smuggle_extra_test(
        self, handle: str, evidence: EvidenceBundle, extra_id: str
    ) -> OracleResult:
        records = evidence.test_records + (TestRecord(test_id=extra_id, status="pass"),)
        blob = json.dumps(
            [(r.test_id, r.status) for r in records], sort_keys=True
        ).encode()
        smuggled = EvidenceBundle(
            test_records=records,
            evidence_bytes=blob,
            evidence_sha256=hashlib.sha256(blob).hexdigest(),
        )
        return self.executor.evaluate(handle, smuggled)

    def invoke_revoked_tools(self) -> str:
        """Attempt agent tool use against the revoked surface."""
        surface = self.executor.agent_surface
        try:
            surface.invoke("write_file", path="x.py", content="y")
        except BoundaryRefusal as exc:
            return self._note(exc.code)
        return self._note("NOT_REFUSED")
