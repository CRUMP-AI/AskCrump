from pathlib import Path
import json
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_deadlines_settle_and_preserve_safe_asset_recovery():
    result = subprocess.run(
        [shutil.which('node') or 'node', str(ROOT / 'scripts' / 'verify-workspace-runtime-deadlines.cjs')],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence['success'] is True
    assert evidence['nativeParity'] is True
    assert len(evidence['cases']) == 7
