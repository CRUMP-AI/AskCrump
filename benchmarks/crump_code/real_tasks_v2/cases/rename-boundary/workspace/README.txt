Fix inventory.paths(raw). Parse porcelain-v1 -z status: ordinary records are XY<space>path<NUL>; rename/copy records add source<NUL> after destination. Return sorted unique paths including both sides. Reject a truncated/malformed record, any .env or .git path component, absolute/traversal/backslash paths, and leading/trailing whitespace. Interior spaces are valid; empty inventory returns [].

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
