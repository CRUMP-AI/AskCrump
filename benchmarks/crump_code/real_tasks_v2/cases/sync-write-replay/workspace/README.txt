Fix sync.push and store.MemoryStore. Replaying the same owner/chat/revision after a dropped response must not append another conversation. A newer revision replaces its value; an older/equal revision is ignored. push must opt in to the transport's retry_transient switch, preserve owner isolation and return the accepted/ignored result.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
