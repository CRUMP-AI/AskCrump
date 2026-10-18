from lifecycle import expire
async def list_tasks(db,now):
    rows=await db.select(["id","owner","status","expires","receipt","lease"])
    result=[await expire(db,row,now) for row in rows]
    return [{key:row[key] for key in ("id","status","failure_code") if key in row} for row in result]
