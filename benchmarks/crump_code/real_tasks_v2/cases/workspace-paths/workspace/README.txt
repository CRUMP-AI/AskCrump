Fix paths.normalize(value). Accept only nonempty canonical relative POSIX source paths ending .py/.js/.txt/.md. Reject leading/trailing whitespace, slash/backslash roots, drive names, repeated separators, dot/dotdot components, control characters and any case-insensitive .git/.env component. Return input unchanged when valid. No filesystem access belongs in this pure canonicalizer.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
