from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sys

TARGETS = {
    "backend/crump52_patches.py": (
        "import json\nimport logging\n",
        "import logging\n",
    ),
    "backend/intelligence_service.py": (
        "import hashlib\nimport json\nimport re\n",
        "import hashlib\nimport re\n",
    ),
    "scripts/check-javascript.mjs": (
        "  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-v1.js', 'crump-v1-body.js',\n",
        "  'crump-5.2.js', 'crump-5.2.2.js', 'crump-5.2.4.js', 'crump-navigation-5.2.5.js',\n"
        "  'crump-v1.js', 'crump-v1-body.js', 'crump-v1-stability.js',\n",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply Ask Crump Phase 4 CI-health fixes to a local repository."
    )
    parser.add_argument("repo", nargs="?", default=".", help="Path to CRUMP-AI repository root")
    parser.add_argument("--check", action="store_true", help="Validate only; make no changes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".github" / "workflows" / "ci.yml").exists():
        print(f"ERROR: {repo} does not look like the CRUMP-AI repository root.", file=sys.stderr)
        return 2

    pending: list[tuple[Path, str]] = []
    already_fixed: list[str] = []

    for relative, (old, new) in TARGETS.items():
        path = repo / relative
        if not path.exists():
            print(f"ERROR: missing {relative}", file=sys.stderr)
            return 3
        text = path.read_text(encoding="utf-8")
        if old in text:
            if text.count(old) != 1:
                print(f"ERROR: expected exactly one guarded match in {relative}.", file=sys.stderr)
                return 4
            pending.append((path, text.replace(old, new, 1)))
        elif new in text:
            already_fixed.append(relative)
        else:
            print(
                f"ERROR: {relative} has diverged from the audited main branch. "
                "Do not guess; merge PATCHES/phase4-ci-health.diff manually.",
                file=sys.stderr,
            )
            return 5

    print("Validated Phase 4 CI targets.")
    if already_fixed:
        print("Already fixed: " + ", ".join(already_fixed))
    if args.check:
        print(f"Would update {len(pending)} file(s). No files changed.")
        return 0
    if not pending:
        print("Nothing to change.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = repo / f"BACKUP-PHASE4-CI-{stamp}"
    for path, _ in pending:
        relative = path.relative_to(repo)
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    for path, new_text in pending:
        path.write_text(new_text, encoding="utf-8")

    print(f"Updated {len(pending)} file(s).")
    print(f"Backup created at: {backup}")
    print("Next: review the diff in GitHub Desktop, then commit/push.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
