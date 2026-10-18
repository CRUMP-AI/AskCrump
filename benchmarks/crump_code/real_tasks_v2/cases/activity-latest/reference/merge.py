from copy import deepcopy
def merge(*batches):
    found = {}
    for batch in batches:
        for item in batch:
            key = item.get("id")
            if key and (key not in found or item["stamp"] >= found[key]["stamp"]):
                found[key] = deepcopy(item)
    return list(found.values())
