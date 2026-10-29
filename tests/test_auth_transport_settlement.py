from pathlib import Path
import shutil
import subprocess


def test_auth_transport_settles_and_preserves_unverified_sessions():
    root = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    assert node, 'Node is required for the executable auth transport regression'
    subprocess.run(
        [node, str(root / 'scripts' / 'verify-auth-transport-settlement.cjs')],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
