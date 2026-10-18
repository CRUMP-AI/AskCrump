Fix transport.request(send, method, max_attempts=4). send is async and yields an HTTP status or raises ConnectionError. Retry GET/HEAD on connection failures and 408/500/502/503/504/520 up to the bound, yielding between attempts. Never retry another method or permanent status; propagate an exhausted connection error.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
