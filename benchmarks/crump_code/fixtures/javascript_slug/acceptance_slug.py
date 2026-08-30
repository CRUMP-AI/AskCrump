import json
import os
import subprocess


MODULE = "./benchmarks/crump_code/fixtures/javascript_slug/slug.js"
NODE = os.environ.get("CRUMP_BENCHMARK_NODE", "node")


def slug(value: str) -> str:
    script = (
        f"import {{ slugify }} from {json.dumps(MODULE)};"
        f"process.stdout.write(slugify({json.dumps(value)}));"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout


def test_slugify_normalizes_spacing_and_punctuation():
    assert slug("  Quarterly   Plan  ") == "quarterly-plan"
    assert slug("Hello, world!") == "hello-world"


def test_slugify_collapses_existing_separators():
    assert slug("Ask___Crump---Workspace") == "ask-crump-workspace"


def test_slugify_returns_an_empty_slug_for_non_words():
    assert slug(" ... ") == ""
