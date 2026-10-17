import asyncio
class Gate:
    def __init__(self): self.state="ready"; self.refunds=0
    async def begin(self):
        allowed=self.state=="ready"
        await asyncio.sleep(0)
        if allowed: self.state="started"
        return allowed
    async def cancel(self):
        refundable=self.state=="ready"
        await asyncio.sleep(0)
        self.state="cancelled"
        if refundable: self.refunds+=1
        return refundable
