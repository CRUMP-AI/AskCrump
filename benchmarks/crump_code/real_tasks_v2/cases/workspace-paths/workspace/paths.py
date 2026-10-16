def normalize(value):
    value=str(value).replace("\\","/").strip(" /")
    if ".." in value: raise ValueError("path")
    return value
