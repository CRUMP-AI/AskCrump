def normalize(value):
    if not isinstance(value,str) or not value or value!=value.strip() or "\\" in value or ":" in value or any(ord(c)<32 for c in value): raise ValueError("path")
    parts=value.split("/")
    if any(p in {"",".",".."} or p.lower() in {".git",".env"} for p in parts): raise ValueError("path")
    if not value.endswith((".py",".js",".txt",".md")): raise ValueError("source")
    return value
