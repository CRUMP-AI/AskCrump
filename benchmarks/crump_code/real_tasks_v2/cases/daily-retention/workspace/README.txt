Fix ledger.Ledger. reserve(id,day,amount,cap) must reject duplicate IDs and daily overflow, preserving the strictest admitted cap. settle changes that reservation's held cost to actual (or max(reserved,actual) when uncertain); release holds0; erase removes only identifiable reservation data, not historical day totals/caps. Late settlement updates original day. Reject noninteger/negative amounts and settlement on absent IDs. totals(day) returns (held,cap) or (0,None).

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
