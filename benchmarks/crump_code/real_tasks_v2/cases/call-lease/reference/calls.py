import asyncio
class Calls:
    def __init__(self): self.rows={}; self.lock=asyncio.Lock()
    async def reserve(self,key,digest,lease):
        async with self.lock:
            if key in self.rows:
                row=self.rows[key]
                if row["digest"]!=digest or row["status"]!="reserved": raise ValueError("replay")
                row["lease"]=lease
            else: self.rows[key]={"digest":digest,"lease":lease,"status":"reserved"}
            return dict(self.rows[key])
    async def begin(self,key,lease):
        async with self.lock:
            row=self.rows[key]
            if row["lease"]!=lease: raise ValueError("owner")
            if row["status"]!="reserved": return False
            row["status"]="started"; return True
