Fix recovery.sanitize(item). Return a fresh dict with role/content only, plus recognized replyErrorCode/replyRecovery for USER messages. Codes IMAGE_SAFETY_REJECTED expect changeRequired prompt_or_reference; INVALID_IMAGE_EDIT_SOURCE/IMAGE_EDIT_SOURCE_TOO_LARGE expect reference. Recovery action must be revise_image_request and usageRestored strictly True. Missing changeRequired on old records defaults by code; a mismatched value is rejected. Drop arbitrary metadata and never mutate input.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
