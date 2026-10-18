from lifecycle import expire
async def list_tasks(db,now):
    rows=await db.select(["id","status","expires"])
    return [await expire(db,row,now) for row in rows]
