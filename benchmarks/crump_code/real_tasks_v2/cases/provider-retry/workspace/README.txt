Fix policy.retryable and worker.process. A provider_started marker forbids any automatic retry, including unexpected exceptions. Before it starts, retry only declared transient failures below max_attempts; missing/unknown failures terminate. process returns completed on success, retrying on a permitted retry and failed otherwise, with one run invocation.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
