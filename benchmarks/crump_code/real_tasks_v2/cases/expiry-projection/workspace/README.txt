Fix query.list_tasks and lifecycle.expire. DB projection is real: it returns only requested fields. Reconcile expired rows using owner, receipt and lease, mark paid unstarted work refund_pending, and use the lease as an optimistic filter. Public results contain only id/status/failure_code. Unexpired rows must not be written; preserve canonical owner and never leak receipt/lease.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
