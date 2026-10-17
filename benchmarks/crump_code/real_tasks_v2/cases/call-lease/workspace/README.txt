Fix calls.Calls. reserve(key,digest,lease) is idempotent only for the same digest while still reserved; a new lease may take that unused reservation. begin(key,lease) atomically returns True once for current owner, sets started, and later begins always return False. Wrong owners/different digest/reserving a started call raise ValueError without mutations. At most one concurrent begin may win.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
