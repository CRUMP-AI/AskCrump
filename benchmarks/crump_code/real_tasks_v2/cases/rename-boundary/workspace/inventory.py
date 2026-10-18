def paths(raw):
    return sorted({line[3:].strip().split(" -> ")[-1] for line in raw.splitlines() if line})
