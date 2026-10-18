class MemoryStore:
    def __init__(self): self.rows = []
    async def apply(self, owner, item):
        self.rows.append({"owner":owner, **item})
        return "accepted"
