def merge(*batches):
    found = {}
    for batch in batches:
        for item in batch:
            if item.get("id") and item["id"] not in found:
                found[item["id"]] = item
    return list(found.values())
