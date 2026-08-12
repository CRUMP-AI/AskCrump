from __future__ import annotations

from pathlib import Path
import ast
import os
import shutil
import subprocess
import sys


def looks_like_repo(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / '.git').exists()
        and (path / '.github' / 'workflows' / 'ci.yml').exists()
        and (path / 'backend' / 'crump52_patches.py').exists()
        and (path / 'scripts' / 'check-javascript.mjs').exists()
    )


def discover_repos() -> list[Path]:
    home = Path.home()
    direct = [
        home / 'Documents' / 'GitHub' / 'CRUMP-AI',
        home / 'Documents' / 'GitHub' / 'CRUMP-AI-main',
        home / 'GitHub' / 'CRUMP-AI',
        home / 'GitHub' / 'CRUMP-AI-main',
        home / 'Desktop' / 'CRUMP-AI',
        home / 'Desktop' / 'CRUMP-AI-main',
        home / 'OneDrive' / 'Documents' / 'GitHub' / 'CRUMP-AI',
        home / 'OneDrive' / 'Documents' / 'GitHub' / 'CRUMP-AI-main',
    ]
    found: list[Path] = []
    for candidate in direct:
        if looks_like_repo(candidate.resolve()) and candidate.resolve() not in found:
            found.append(candidate.resolve())
    if found:
        return found

    # Bounded fallback search. Avoid large/generated/system trees.
    skip = {'AppData', 'node_modules', '.venv', 'venv', '.cache', 'Library', 'Pictures', 'Music', 'Videos'}
    home_parts = len(home.parts)
    for root, dirs, _files in os.walk(home):
        root_path = Path(root)
        depth = len(root_path.parts) - home_parts
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith('$')]
        if depth > 5:
            dirs[:] = []
            continue
        if root_path.name.lower() in {'crump-ai', 'crump-ai-main'} and looks_like_repo(root_path):
            resolved = root_path.resolve()
            if resolved not in found:
                found.append(resolved)
            dirs[:] = []
    return found


def choose_repo() -> Path:
    repos = discover_repos()
    if len(repos) == 1:
        print(f'Found CRUMP-AI repository: {repos[0]}')
        return repos[0]
    if len(repos) > 1:
        print('Multiple CRUMP-AI repositories were found:')
        for idx, repo in enumerate(repos, 1):
            print(f'  {idx}. {repo}')
        while True:
            choice = input('Enter the number for the repository used by GitHub Desktop: ').strip()
            try:
                selected = repos[int(choice) - 1]
                return selected
            except (ValueError, IndexError):
                print('Please enter one of the numbers shown above.')

    print('I could not automatically locate the repository.')
    print('In GitHub Desktop choose Repository > Show in Explorer, then copy the folder path.')
    while True:
        raw = input('Paste the CRUMP-AI repository folder path here: ').strip().strip('"')
        candidate = Path(raw).expanduser().resolve()
        if looks_like_repo(candidate):
            return candidate
        print('That folder does not look like the CRUMP-AI repository. Try again.')


repo = choose_repo()

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
planned: dict[Path, str] = {}

print('\nValidating audited source...')
for path, (old, new) in changes.items():
    text = path.read_text(encoding='utf-8')
    originals[path] = text
    if new in text and old not in text:
        planned[path] = text
        print(f'  already fixed: {path.relative_to(repo)}')
        continue
    if text.count(old) != 1:
        print(f'ERROR: {path.relative_to(repo)} has diverged from the audited source.')
        print('No source files were changed.')
        raise SystemExit(4)
    planned[path] = text.replace(old, new, 1)
    print(f'  ready: {path.relative_to(repo)}')

# Apply only after all guards succeed.
for path, text in planned.items():
    path.write_text(text, encoding='utf-8')

try:
    for rel in ('backend/crump52_patches.py', 'backend/intelligence_service.py'):
        ast.parse((repo / rel).read_text(encoding='utf-8'), filename=rel)

    node = shutil.which('node')
    if node:
        check = subprocess.run([node, '--check', str(repo / 'scripts' / 'check-javascript.mjs')], cwd=repo)
        if check.returncode != 0:
            raise RuntimeError('JavaScript syntax validation failed.')
        contract = subprocess.run([node, str(repo / 'scripts' / 'check-javascript.mjs')], cwd=repo)
        if contract.returncode != 0:
            raise RuntimeError('Ask Crump JavaScript contract validation failed.')
except Exception as exc:
    for path, text in originals.items():
        path.write_text(text, encoding='utf-8')
    print(f'ERROR: Validation failed. Source files were restored. {exc}')
    raise SystemExit(5)

# Remove only the Phase 4 handoff artifacts that were accidentally committed.
remove_paths = [
    repo / 'APPLY_PHASE4_CI_FIX.py',
    repo / 'APPLY_PHASE4_FIX.bat',
    repo / '_phase4_fix.py',
    repo / 'PATCHES' / 'phase4-ci-health.diff',
]
for path in remove_paths:
    if path.exists():
        try:
            path.unlink()
            print(f'Removed accidental handoff artifact: {path.relative_to(repo)}')
        except OSError as exc:
            print(f'WARNING: Could not remove {path.relative_to(repo)}: {exc}')

print('\n=========================================================')
print('PHASE 4 REAL SOURCE FIX APPLIED SUCCESSFULLY')
print('=========================================================')
print('Open GitHub Desktop now.')
print('You should see edits to:')
print('  backend/crump52_patches.py')
print('  backend/intelligence_service.py')
print('  scripts/check-javascript.mjs')
print('and deletions of the accidental Phase 4 helper files.')
print('\nCommit title: Apply real Phase 4 CI source fixes')
print('Push the commit, then tell Echo: Phase 4 real source fix pushed.')
