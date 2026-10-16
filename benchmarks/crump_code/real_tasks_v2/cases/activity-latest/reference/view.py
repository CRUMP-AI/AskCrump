from merge import merge
ACTIVE = {"queued", "running", "verifying"}
def activity(batches, limit=18):
    rows = [row for row in merge(*batches)
            if row["status"] != "queued" or row.get("paid")]
    return sorted(rows, key=lambda row: (row["status"] not in ACTIVE, -row["stamp"]))[:max(0, limit)]
