def read_patch(read_bytes, limit):
    if type(limit) is not int or limit < 0: raise ValueError("limit")
    try: data=read_bytes()
    except OSError as exc: raise ValueError("missing") from exc
    if not isinstance(data,bytes) or len(data)>limit: raise ValueError("incomplete")
    try: return data.decode("utf-8")
    except UnicodeError as exc: raise ValueError("encoding") from exc
