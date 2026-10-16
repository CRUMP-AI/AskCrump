Fix repair.run(workspace, propose, max_turns). Each iteration calls async propose(last_feedback), then async workspace.verify(). Ignore propose's success claims; only a dict receipt with strict integer returnCode0 and revision==workspace.revision completes. Feed the actual failed/stale receipt to the next propose unchanged. All attempts/repairs share max_turns; invalid/zero/bool limits reject before callbacks. On exhaustion return failed; never call propose after a verified success.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
