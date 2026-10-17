async def expire(db,row,now):
    if row["expires"]<=now:
        changes={"status":"cancelled","failure_code":"expired"}
        if row.get("receipt"): changes["payment_source"]="refund_pending"
        filters={"lease":row["lease"]} if row.get("lease") else {}
        return await db.update(row["id"],row["owner"],filters,changes)
    return row
