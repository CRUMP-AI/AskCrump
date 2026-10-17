"""Negative tests for the v2 status generator: strict booleans, ID integrity,
suite/manifest binding, strata, counts, timestamps, and honest aggregate text.

The generator must REFUSE to label (SystemExit) rather than silently coerce
or drop data. Authored fixture checks are NOT model quality results.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.crump_code_v2_status import (
    AGGREGATE,
    DEFAULT_CORPUS,
    HONEST_STATE,
    build_status,
)


def mutated_corpus(tmp_path, mutate):
    root = tmp_path / "corpus"
    shutil.copytree(DEFAULT_CORPUS, root)
    path = root / "solvability.v2.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutate(doc)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return root


def set_row(doc, index, **fields):
    for key, value in fields.items():
        doc["cases"][index][key] = value


def test_valid_corpus_builds_all_not_evaluated(tmp_path):
    root = tmp_path / "corpus"
    shutil.copytree(DEFAULT_CORPUS, root)
    status = build_status(root)
    assert len(status["cases"]) == 20
    assert all(
        c["label"] == "Not evaluated" and c["reason"] == "model evaluation not run"
        for c in status["cases"]
    )
    assert status["honest_state"] == HONEST_STATE
    assert status["labels"]["not_evaluated"] == 20


@pytest.mark.parametrize("bad", ["false", "true", "0", "1", "", 0, 1, None])
def test_truthy_string_or_nonbool_success_rejected(tmp_path, bad):
    root = mutated_corpus(tmp_path, lambda doc: doc.update(success=bad))
    with pytest.raises(SystemExit):
        build_status(root)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("baseline_rejected", "false"),
        ("baseline_rejected", "true"),
        ("reference_accepted", "false"),
        ("reference_accepted", "true"),
        ("baseline_rejected", 1),
        ("reference_accepted", 0),
    ],
)
def test_truthy_string_plumbing_booleans_rejected(tmp_path, field, bad):
    def mutate(doc):
        set_row(doc, 0, **{field: bad})

    root = mutated_corpus(tmp_path, mutate)
    with pytest.raises(SystemExit):
        build_status(root)


def test_false_plumbing_booleans_refuse_without_coercion(tmp_path):
    def mutate(doc):
        set_row(doc, 0, baseline_rejected=False)

    root = mutated_corpus(tmp_path, mutate)
    with pytest.raises(SystemExit):
        build_status(root)


def test_duplicate_row_ids_rejected(tmp_path):
    def mutate(doc):
        doc["cases"] = doc["cases"][:19] + [copy.deepcopy(doc["cases"][0])]

    root = mutated_corpus(tmp_path, mutate)
    with pytest.raises(SystemExit):
        build_status(root)


def test_extra_row_id_rejected(tmp_path):
    def mutate(doc):
        invented = copy.deepcopy(doc["cases"][0])
        invented["id"] = "invented-case"
        doc["cases"] = doc["cases"][:19] + [invented]

    root = mutated_corpus(tmp_path, mutate)
    with pytest.raises(SystemExit):
        build_status(root)


def test_wrong_row_count_rejected(tmp_path):
    root = mutated_corpus(tmp_path, lambda doc: doc.update(cases=doc["cases"][:-1]))
    with pytest.raises(SystemExit):
        build_status(root)


@pytest.mark.parametrize("field", ["suite_id", "manifest_sha256"])
def test_suite_manifest_binding_mismatch_rejected(tmp_path, field):
    root = mutated_corpus(tmp_path, lambda doc: doc.update({field: "0" * 64}))
    with pytest.raises(SystemExit):
        build_status(root)


def test_stratum_mismatch_rejected(tmp_path):
    def mutate(doc):
        set_row(
            doc,
            0,
            stratum="bounded"
            if doc["cases"][0]["stratum"] != "bounded"
            else "adversarial",
        )

    root = mutated_corpus(tmp_path, mutate)
    with pytest.raises(SystemExit):
        build_status(root)


@pytest.mark.parametrize(
    "bad_ts",
    [
        "not-a-time",
        "2026-10-17",  # date only, no time
        "2026-10-17T20:43:50.136076",  # naive, no timezone
        "2999-01-01T00:00:00+00:00",  # future
        "",
    ],
)
def test_bad_timestamps_rejected(tmp_path, bad_ts):
    def mutate(doc):
        set_row(doc, 3, last_verified_solvable_at=bad_ts)

    root = mutated_corpus(tmp_path, mutate)
    with pytest.raises(SystemExit):
        build_status(root)


def test_fixture_sha_mismatch_rejected(tmp_path):
    def mutate(doc):
        set_row(doc, 5, fixture_sha256="f" * 64)

    root = mutated_corpus(tmp_path, mutate)
    with pytest.raises(SystemExit):
        build_status(root)


def test_aggregate_language_is_honest(tmp_path):
    root = tmp_path / "corpus"
    shutil.copytree(DEFAULT_CORPUS, root)
    status = build_status(root)
    assert (
        status["aggregate"]
        == AGGREGATE
        == "Model evaluation not run; 0 cases evaluated; fix rate unavailable"
    )
    assert status["fix_rate"] is None
    dumped = json.dumps(status)
    assert "0/20" not in dumped
    assert "sandboxed harness" not in dumped
    assert "fix rate unavailable" in status["aggregate"]
