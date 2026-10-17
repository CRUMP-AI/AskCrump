Fix writer.write(fs, git, path, content). git.check_ignore returns async status0 ignored,1 eligible (including tracked files matching a pattern),other unknown. Reject ignored with ValueError and unknown with RuntimeError before creating a directory or writing. On1, mkdir the parent if needed then write and return the path; never reinterpret a tracked file based on pattern text.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
