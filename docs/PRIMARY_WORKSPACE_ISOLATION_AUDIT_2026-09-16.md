# Primary workspace isolation audit — 2026-09-16

State: **PRESERVE / DO NOT USE AS A RELEASE SOURCE**

## Finding

The long-lived workspace at
`C:\Users\gcrum\OneDrive\Documents\GitHub\CRUMP-AI-Portfolio-Upload` is not a clean current-main
checkout:

- local `main` HEAD: `86cd73feabc6b65b809999c5efc45dec239f3b68`;
- `origin/main` / exact production source: `7833d89e2e5ee419fd27757f82c4fff92beed295`;
- local `main` is **390 commits behind** with no local branch commit ahead;
- the merge base is the local `main` HEAD;
- the index contains no staged change;
- porcelain status contains 115 modified tracked entries and 113 untracked entries;
- `git ls-files --others --exclude-standard` expands untracked directories to 145 individual paths;
  and
- comparison against exact production reports 551 tracked path differences. That count mixes local
  edits with files added, removed, or changed during the 390 intervening commits and must not be
  interpreted as 551 independent customer-facing defects.

The untracked and modified names span application code, tests, release evidence, staged campaigns,
media/realtime candidates, and generated output. They may contain valuable historical or
user-owned work.

## Action taken

None of that workspace state was modified. No reset, clean, checkout, rebase, merge, stash, move,
delete, commit, or branch-pointer update was attempted.

Current product and release work remains anchored to clean, exact-base worktrees:

- production source: `C:\AskCrump-Guide-CTA-Review-20260908` at `7833d89`;
- held output-continuity candidate: `C:\AskCrump-Artifact-Continuity-Dedupe-20260916` at `9ad93c8`;
- held campaign candidates remain in their own named worktrees.

## Release rule

Do not run a production build, merge, deployment, migration, or broad cleanup from the long-lived
dirty workspace. Before reclaiming it, make a separately authorized recovery plan that inventories
and preserves every changed/untracked path, records provenance, creates a recoverable snapshot, and
then reconciles it against current `origin/main`. Until then, continue using exact clean worktrees.

This is a release-hygiene boundary, not evidence that the preserved files are wrong or disposable.
