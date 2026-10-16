Fix artifact.read_patch(read_bytes, limit). Return the complete UTF-8 text only when its byte count is at most limit. A larger, invalid UTF-8, missing, or non-byte artifact must raise ValueError, never yield a shortened or replacement-decoded artifact. Empty bytes are valid; bool/negative/non-integer limits are invalid.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
