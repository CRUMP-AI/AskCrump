Fix budget.reserve(body, policy). Exact model must match; max_tokens strict int1..max_output; UTF-8 canonical JSON of ALL fields (including tools/system) must fit max_bytes and reject NaN. Price ceiling is ceil(((bytes+4096)*input_rate + max_tokens*output_rate)/1_000_000). Return digest/cost/input_ceiling; reject ceiling above call_limit, invalid shape or nonpositive limits/rates. Never mutate body.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
