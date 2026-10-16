async def push(db, owner, item):
    return await db.write(owner, dict(item), retry_transient=False)
