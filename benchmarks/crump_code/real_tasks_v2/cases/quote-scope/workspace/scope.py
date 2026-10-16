import hashlib
def digest(scope): return hashlib.sha256(str(scope).encode()).hexdigest()
