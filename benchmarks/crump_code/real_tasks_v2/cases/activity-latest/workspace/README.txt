Repair merge.py and view.py. A task may appear in multiple asynchronous reads. Keep the snapshot with the newest stamp (later read wins a tie), then show active tasks before terminal tasks, newest first within each group. Exclude undispatched queued drafts, ignore missing IDs, respect limit, and do not mutate inputs.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
