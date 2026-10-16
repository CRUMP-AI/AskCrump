import asyncio
class Gate:
    def __init__(self): self.state="ready"; self.refunds=0; self.lock=asyncio.Lock()
    async def begin(self):
        async with self.lock:
            if self.state!="ready": return False
            self.state="started"; return True
    async def cancel(self):
        async with self.lock:
            refundable=self.state=="ready"
            self.state="cancelled"
            if refundable: self.refunds+=1
            return refundable
