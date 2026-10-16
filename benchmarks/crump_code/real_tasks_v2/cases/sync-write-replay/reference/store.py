import asyncio
from copy import deepcopy
class MemoryStore:
    def __init__(self): self.rows = []; self.lock=asyncio.Lock()
    async def apply(self, owner, item):
        async with self.lock:
            for index,row in enumerate(self.rows):
                if row["owner"]==owner and row["id"]==item["id"]:
                    if row["revision"]>=item["revision"]: return "ignored"
                    self.rows[index]={**deepcopy(item),"owner":owner}; return "accepted"
            self.rows.append({**deepcopy(item),"owner":owner}); return "accepted"
