Fix scope.digest and dispatch.authorized. Scope hashing must be deterministic canonical JSON, independent of dictionary insertion order. A 12-credit confirmation is valid only for exactly this owner, task ID, and mode; reject any changed field and every non-integer/bool/insufficient amount before calling charge. Return the canonical charge receipt unchanged.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
