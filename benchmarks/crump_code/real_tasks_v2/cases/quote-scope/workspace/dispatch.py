from scope import digest
async def authorized(task, confirmation, charge):
    if confirmation["scope"] != digest({"owner":task["owner"]}): raise ValueError("scope")
    return await charge(confirmation["credits"])
