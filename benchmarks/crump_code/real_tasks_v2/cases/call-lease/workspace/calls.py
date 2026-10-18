import asyncio
class Calls:
    def __init__(self): self.rows={}
    async def reserve(self,key,digest,lease):
        self.rows[key]={"digest":digest,"lease":lease,"status":"reserved"}
        return dict(self.rows[key])
    async def begin(self,key,lease):
        allowed=self.rows[key]["status"]=="reserved"
        await asyncio.sleep(0)
        self.rows[key]["status"]="started"
        return allowed
