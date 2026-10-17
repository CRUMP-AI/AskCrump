Fix workspace.Workspace and verdict.verdict. Every edit increments generation; checks record current generation, command and return code. Verdict is completed only if each required command's latest check at the FINAL generation has integer code0. Old failures can be repaired by a later passing check; checks before the last edit do not count. Empty requirements/invalid/null/bool codes cannot certify changed work. Unchanged work completes without checks.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
