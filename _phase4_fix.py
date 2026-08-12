from __future__ import annotations

from pathlib import Path
import ast
import shutil
import subprocess
import sys

repo = Path(__file__).resolve().parent

required = repo / '.github' / 'workflows' / 'ci.yml'
if not required.exists():
    print('ERROR: Put APPLY_PHASE4_FIX.bat and _phase4_fix.py in the ROOT of your CRUMP-AI repository, then run APPLY_PHASE4_FIX.bat.')
    raise SystemExit(2)

changes = {
    repo / 'backend' / 'crump52_patches.py': (
        'import json\nimport logging\n',
        'import logging\n',
    ),
    repo / 'backend' / 'intelligence_service.py': (
        'import hashlib\nimport json\nimport re\n',
        'import hashlib\nimport re\n',
    ),
    repo / 'scripts' / 'check-javascript.mjs': (
        "  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-v1.js', 'crump-v1-body.js',\n",
        "  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-navigation-5.2.5.js',\n"
        "  'crump-v1.js', 'crump-v1-body.js', 'crump-v1-stability.js',\n",
    ),
}

originals: dict[Path, str] = {}
new_values: dict[Path, str] = {}

for path, (old, new) in changes.items():
    if not path.exists():
        print(f'ERROR: Missing {path.relative_to(repo)}')
        raise SystemExit(3)
    text = path.read_text(encoding='utf-8')
    originals[path] = text
    if new in text and old not in text:
        new_values[path] = text
        continue
    if text.count(old) != 1:
        print(f'ERROR: {path.relative_to(repo)} does not match the audited source. Nothing was changed.')
        raise SystemExit(4)
    new_values[path] = text.replace(old, new, 1)

for path, text in new_values.items():
    path.write_text(text, encoding='utf-8')

try:
    for rel in ('backend/crump52_patches.py', 'backend/intelligence_service.py'):
        ast.parse((repo / rel).read_text(encoding='utf-8'), filename=rel)

    node = shutil.which('node')
    if node:
        result = subprocess.run([node, '--check', str(repo / 'scripts' / 'check-javascript.mjs')], cwd=repo)
        if result.returncode != 0:
            raise RuntimeError('JavaScript syntax validation failed.')

        result = subprocess.run([node, str(repo / 'scripts' / 'check-javascript.mjs')], cwd=repo)
        if result.returncode != 0:
            raise RuntimeError('Ask Crump JavaScript contract validation failed.')
except Exception as exc:
    for path, text in originals.items():
        path.write_text(text, encoding='utf-8')
    print(f'ERROR: Validation failed; source files were restored. {exc}')
    raise SystemExit(5)

for rel in ('APPLY_PHASE4_CI_FIX.py', 'PATCHES/phase4-ci-health.diff'):
    path = repo / rel
    try:
        if path.exists():
            path.unlink()
            print(f'Removed old handoff artifact: {rel}')
    except OSError as exc:
        print(f'WARNING: Could not remove {rel}: {exc}')

print('')
print('PHASE 4 SOURCE FIX APPLIED AND VALIDATED.')
print('GitHub Desktop should now show the three real source edits, plus deletion of the two old handoff artifacts if they were present.')
print('Commit and push those changes. No Vercel environment values need to be entered again.')
