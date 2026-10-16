Fix tokens.verify and admission.admit. This ORIGINAL stdlib HMAC fixture is an analogue, NOT production RS256/OIDC. Format payload_hex.signature_hex; signature is HMAC-SHA256 over payload bytes with provided key. Verify signature BEFORE trusting JSON, require a dict, strict integer exp>now and exact issuer/audience/project/team/environment policy. Return only project/team; invalid envelopes raise ValueError before provision. Policy comes from the caller, never token claims.

Run visible checks with: python3 -m unittest discover -s tests -v
Only the listed source modules may change. Tests and this description are immutable. Hidden acceptance checks are evaluator-owned.
This restricted corpus permits stdlib asyncio/copy/datetime/hashlib/hmac/json/math/collections/dataclasses/re/typing/decimal, pathlib.PurePosixPath, and sibling source modules. No filesystem/process/network I/O, harness introspection, module monkeypatches, or dynamic execution.
