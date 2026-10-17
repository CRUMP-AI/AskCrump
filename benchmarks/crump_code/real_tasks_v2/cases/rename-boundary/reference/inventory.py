def paths(raw):
    if not isinstance(raw,str) or (raw and not raw.endswith("\0")): raise ValueError("truncated")
    entries=raw.split("\0"); output=[]; index=0
    while index<len(entries)-1:
        entry=entries[index]; index+=1
        if len(entry)<4 or entry[2]!=" " or any(c not in " MADRCU?!" for c in entry[:2]): raise ValueError("record")
        candidates=[entry[3:]]
        if "R" in entry[:2] or "C" in entry[:2]:
            if index>=len(entries)-1: raise ValueError("rename")
            candidates.append(entries[index]); index+=1
        for path in candidates:
            parts=path.split("/")
            if path!=path.strip() or "\\" in path or ":" in path or any(p in {"",".","..",".env",".git"} for p in parts): raise ValueError("path")
            output.append(path)
    return sorted(set(output))
