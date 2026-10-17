from merge import merge
ACTIVE = {"queued", "running", "verifying"}
def activity(batches, limit=18):
    rows = merge(*batches)
    return sorted(rows, key=lambda row: row["stamp"], reverse=True)[:limit]
