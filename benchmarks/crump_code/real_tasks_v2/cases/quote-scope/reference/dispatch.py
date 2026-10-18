from scope import digest
async def authorized(task, confirmation, charge):
    expected={key:task[key] for key in ("owner","id","mode")}
    if confirmation.get("scope") != digest(expected): raise ValueError("scope")
    amount=confirmation.get("credits")
    if type(amount) is not int or amount != 12: raise ValueError("credits")
    return await charge(12)
