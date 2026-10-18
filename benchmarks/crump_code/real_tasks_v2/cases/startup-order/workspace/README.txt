Fix startup.Boot. An armed demo installs its interceptor immediately on construction, but enters only after shell_ready or dom_ready. Any event order/repetition enters once. On dom_ready, register the demo chats renderer once even if already entered; DOM fallback permits a missing shell. Unarmed boot must never intercept, enter or register. Use callbacks, no global state.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
