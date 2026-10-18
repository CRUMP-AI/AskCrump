Fix sizing.prepare(width,height,max_edge,max_pixels,encoded_bytes,max_bytes). Validate strict positive integer dimensions/limits and nonnegative integer byte count. Reject encoded_bytes>=max_bytes. Downscale only: one aspect-preserving scale=min(1,edge/maxdimension,sqrt(pixelcap/area)), floor each result with minimum1; final area and edge must fit, never upscale. No image library or I/O needed.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
