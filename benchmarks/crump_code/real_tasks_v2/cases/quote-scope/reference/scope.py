import hashlib
import json
def digest(scope):
    return hashlib.sha256(json.dumps(scope,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
