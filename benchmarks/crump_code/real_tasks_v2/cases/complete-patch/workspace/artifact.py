def read_patch(read_bytes, limit):
    return read_bytes()[:limit].decode("utf-8",errors="replace")
